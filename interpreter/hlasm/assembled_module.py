# pyright: standard
"""The object module of an assembly: ESD from its sections, ENTRY names, external symbols and external dummy sections, TXT and RLD from its placed constants (an address in a DSECT is its offset, with no RLD; Q, J and CXD are RLD alone; a complex-relocatable constant is one signed RLD per term outside a DSECT, the first carrying the absolute part), END from its entry point."""

from collections.abc import Mapping
from itertools import chain, repeat

from hlasm_asg.program.complex_address import ComplexAddress
from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.external_dummy import ExternalDummy
from hlasm_asg.program.external_kind import ExternalKind
from hlasm_asg.program.external_symbol import ExternalSymbol
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.named_entry import NamedEntry
from hlasm_asg.program.reloc_symbol import RelocSymbol
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from hlasm_asg.program.term_kind import TermKind
from hlasm_asg.program.term_sign import TermSign
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.binder_slot import BinderSlot
from interpreter.hlasm.complex_slot import ComplexSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.entry_state import resolve_entry
from interpreter.hlasm.external_slot import ExternalSlot
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE
from interpreter.hlasm.placed_piece import PlacedPiece
from interpreter.hlasm.storage_layout import placed_pieces
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.default_end import DefaultEnd
from interpreter.project.entry_label import EntryLabel
from interpreter.project.esd_record import EsdRecord
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.external_reference import ExternalReference
from interpreter.project.module_end import ModuleEnd
from interpreter.project.named_end import NamedEnd
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_name import RelocationName
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.text_record import TextRecord
from interpreter.project.weak_reference import WeakReference


def _section(section: Section) -> EsdRecord:
    match section.kind:
        case SectionKind.COM:
            return CommonSection(section.name, section.length)
        case _:
            return ControlSection(section.name, section.length)


def _entry_label(program: HlasmProgram, name: str) -> EsdRecord:
    symbol = next(
        s for s in program.symbols if isinstance(s, RelocSymbol) and s.name == name
    )
    return EntryLabel(name, symbol.section, symbol.offset)


def _external(symbol: ExternalSymbol) -> EsdRecord:
    match symbol.kind:
        case ExternalKind.EXTRN:
            return ExternalReference(symbol.name, symbol.line)
        case ExternalKind.WXTRN:
            return WeakReference(symbol.name)


def _relocation(
    placed: PlacedPiece, target: str, addend: int, width: int
) -> RelocationRecord:
    return RelocationRecord(
        placed.section,
        placed.offset,
        width,
        RelocationKind.ADDRESS,
        RelocationName(target),
        RelocationSign.PLUS,
        addend,
    )


_SIGNS: Mapping[TermSign, RelocationSign] = {
    TermSign.PLUS: RelocationSign.PLUS,
    TermSign.MINUS: RelocationSign.MINUS,
}


def _offset_image(offset: int, width: int) -> ConstantImage:
    value = offset % (1 << (BITS_PER_BYTE * width))
    return ConstantImage(tuple(value.to_bytes(width, "big")))


def _in_dummy(placed: PlacedPiece, dummies: frozenset[str]) -> PlacedPiece:
    match placed.piece:
        case AddressSlot(address=address, width=width) if address.section in dummies:
            image = _offset_image(address.offset, width)
            return PlacedPiece(placed.section, placed.offset, image)
        case _:
            return placed


def _undummied(
    slot: ComplexSlot, dummies: frozenset[str]
) -> ComplexSlot | ConstantImage:
    address = slot.address
    terms = tuple(
        t for t in address.terms if t.kind == TermKind.EXTERNAL or t.name not in dummies
    )
    if not terms:
        return _offset_image(address.offset, slot.width)
    kept = ComplexAddress(kind="COMPLEX", terms=terms, offset=address.offset)
    return ComplexSlot(kept, slot.width)


def _complex_in_dummy(placed: PlacedPiece, dummies: frozenset[str]) -> PlacedPiece:
    match placed.piece:
        case ComplexSlot() as slot:
            piece = _undummied(slot, dummies)
            return PlacedPiece(placed.section, placed.offset, piece)
        case _:
            return placed


def _text(placed: PlacedPiece) -> tuple[TextRecord, ...]:
    match placed.piece:
        case ConstantImage(image=image):
            return (TextRecord(placed.section, placed.offset, bytes(image)),)
        case _:
            return ()


def _address_relocations(placed: PlacedPiece) -> tuple[RelocationRecord, ...]:
    match placed.piece:
        case AddressSlot() as slot:
            section = slot.address.section
            return (_relocation(placed, section, slot.address.offset, slot.width),)
        case ExternalSlot() as external:
            name = external.address.name
            return (_relocation(placed, name, external.address.offset, external.width),)
        case _:
            return ()


def _bound_relocations(placed: PlacedPiece) -> tuple[RelocationRecord, ...]:
    match placed.piece:
        case BinderSlot(kind=kind, target=target, width=width):
            sign = RelocationSign.PLUS
            return (
                RelocationRecord(
                    placed.section, placed.offset, width, kind, target, sign, 0
                ),
            )
        case _:
            return ()


def _complex_relocations(placed: PlacedPiece) -> tuple[RelocationRecord, ...]:
    match placed.piece:
        case ComplexSlot(address=address, width=width):
            addends = chain((address.offset,), repeat(0))
            return tuple(
                RelocationRecord(
                    placed.section,
                    placed.offset,
                    width,
                    RelocationKind.ADDRESS,
                    RelocationName(term.name),
                    _SIGNS[term.sign],
                    addend,
                )
                for term, addend in zip(address.terms, addends, strict=False)
            )
        case _:
            return ()


def _relocations(placed: PlacedPiece) -> tuple[RelocationRecord, ...]:
    return (
        *_address_relocations(placed),
        *_complex_relocations(placed),
        *_bound_relocations(placed),
    )


def _external_dummy(dummy: ExternalDummy) -> EsdRecord:
    return ExternalDummySection(dummy.name, dummy.length, dummy.alignment)


def _end(program: HlasmProgram) -> ModuleEnd:
    entry = resolve_entry(program)
    match program.entry:
        case NamedEntry():
            return NamedEnd(entry.name, entry.section, entry.offset)
        case DefaultEntry():
            return DefaultEnd(entry.section)


def object_module(program: HlasmProgram) -> ObjectModule:
    sections = tuple(s for s in program.sections if s.kind != SectionKind.DSECT)
    dummies = frozenset(s.name for s in program.sections) - {s.name for s in sections}
    pieces = tuple(
        _complex_in_dummy(_in_dummy(placed, dummies), dummies)
        for placed in placed_pieces(program, frozenset(s.name for s in sections))
    )
    return ObjectModule(
        esd=(
            *map(_section, sections),
            *(_entry_label(program, name) for name in program.entries),
            *map(_external, program.externals),
            *map(_external_dummy, program.external_dummies),
        ),
        text=tuple(record for placed in pieces for record in _text(placed)),
        relocations=tuple(
            record for placed in pieces for record in _relocations(placed)
        ),
        end=_end(program),
    )
