# pyright: standard
"""The object module of an assembly: ESD from its sections, ENTRY names and external symbols, TXT and RLD from its placed constants, END from its entry point."""

from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.external_kind import ExternalKind
from hlasm_asg.program.external_symbol import ExternalSymbol
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.named_entry import NamedEntry
from hlasm_asg.program.reloc_symbol import RelocSymbol
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.entry_state import resolve_entry
from interpreter.hlasm.external_slot import ExternalSlot
from interpreter.hlasm.placed_piece import PlacedPiece
from interpreter.hlasm.storage_layout import placed_pieces
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.default_end import DefaultEnd
from interpreter.project.entry_label import EntryLabel
from interpreter.project.esd_record import EsdRecord
from interpreter.project.external_reference import ExternalReference
from interpreter.project.module_end import ModuleEnd
from interpreter.project.named_end import NamedEnd
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
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
            return ExternalReference(symbol.name)
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
        target,
        RelocationSign.PLUS,
        addend,
    )


def _text(placed: PlacedPiece) -> tuple[TextRecord, ...]:
    match placed.piece:
        case ConstantImage(image=image):
            return (TextRecord(placed.section, placed.offset, bytes(image)),)
        case _:
            return ()


def _relocations(placed: PlacedPiece) -> tuple[RelocationRecord, ...]:
    match placed.piece:
        case AddressSlot() as slot:
            section = slot.address.section
            return (_relocation(placed, section, slot.address.offset, slot.width),)
        case ExternalSlot() as external:
            name = external.address.name
            return (_relocation(placed, name, external.address.offset, external.width),)
        case _:
            return ()


def _end(program: HlasmProgram) -> ModuleEnd:
    entry = resolve_entry(program)
    match program.entry:
        case NamedEntry():
            return NamedEnd(entry.name, entry.section, entry.offset)
        case DefaultEntry():
            return DefaultEnd(entry.section)


def object_module(program: HlasmProgram) -> ObjectModule:
    sections = tuple(s for s in program.sections if s.kind != SectionKind.DSECT)
    pieces = placed_pieces(program, frozenset(s.name for s in sections))
    return ObjectModule(
        esd=(
            *map(_section, sections),
            *(_entry_label(program, name) for name in program.entries),
            *map(_external, program.externals),
        ),
        text=tuple(record for placed in pieces for record in _text(placed)),
        relocations=tuple(
            record for placed in pieces for record in _relocations(placed)
        ),
        end=_end(program),
    )
