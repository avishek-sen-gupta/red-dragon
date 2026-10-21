# pyright: standard
"""Run-unit start-up IR that allocates each section and writes its constants and literals."""

from collections.abc import Sequence
from itertools import accumulate, chain

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import DcPiece, dc_alignment, encode_dc
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    INT_TO_BINARY_BYTES,
    SECTION_VAR_PREFIX,
)
from interpreter.hlasm.placed_piece import PlacedPiece
from interpreter.instructions import (
    AllocRegion,
    Binop,
    CallFunction,
    Const,
    InstructionBase,
    LoadVar,
    StoreVar,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName

type Fragment = tuple[Register, tuple[InstructionBase, ...]]


def section_var(name: str) -> VarName:
    return VarName(f"{SECTION_VAR_PREFIX}{name}")


def _reg(prefix: str, role: str) -> Register:
    return Register(f"%{prefix}.{role}")


def _allocate(section: Section) -> tuple[InstructionBase, ...]:
    prefix = f"hlasm.sect.{section.name}"
    size = _reg(prefix, "size")
    region = _reg(prefix, "region")
    return (
        Const.int_(size, section.length),
        AllocRegion(result_reg=region, size_reg=size),
        StoreVar(name=section_var(section.name), value_reg=region),
    )


def _align(offset: int, boundary: int) -> int:
    return -(-offset // boundary) * boundary


def _place_pieces(
    section: str, start: int, pieces: tuple[DcPiece, ...]
) -> tuple[PlacedPiece, ...]:
    offsets = accumulate((piece.width for piece in pieces), initial=start)
    return tuple(
        PlacedPiece(section, offset, piece)
        for offset, piece in zip(offsets, pieces, strict=False)
    )


def _place_items(
    section: str, offset: int, items: Sequence[DcItem]
) -> tuple[PlacedPiece, ...]:
    if not items:
        return ()
    start = _align(offset, dc_alignment(items[0]))
    pieces = encode_dc(items[0])
    end = start + sum(piece.width for piece in pieces)
    return (
        *_place_pieces(section, start, pieces),
        *_place_items(section, end, items[1:]),
    )


def _placed(program: HlasmProgram, sections: frozenset[str]) -> tuple[PlacedPiece, ...]:
    statements = (
        _place_items(s.section, s.offset, s.items)
        for s in program.statements
        if isinstance(s, DcStatement) and s.section in sections
    )
    literals = (
        _place_items(literal.section, literal.offset, (literal.item,))
        for literal in program.literals
        if literal.section in sections
    )
    return tuple(chain.from_iterable(chain(statements, literals)))


def _constant_value(prefix: str, piece: ConstantImage) -> Fragment:
    value = _reg(prefix, "value")
    return value, (Const.int_(value, int.from_bytes(bytes(piece.image), "big")),)


def _address_value(prefix: str, piece: AddressSlot) -> Fragment:
    base, offset, address, modulus, value = (
        _reg(prefix, role) for role in ("base", "offset", "address", "mod", "value")
    )
    return value, (
        LoadVar(result_reg=base, name=section_var(piece.address.section)),
        Const.int_(offset, piece.address.offset),
        Binop(result_reg=address, operator=BinopKind.ADD, left=base, right=offset),
        Const.int_(modulus, 1 << (BITS_PER_BYTE * piece.width)),
        Binop(result_reg=value, operator=BinopKind.MOD, left=address, right=modulus),
    )


def _value(prefix: str, piece: DcPiece) -> Fragment:
    match piece:
        case ConstantImage():
            return _constant_value(prefix, piece)
        case AddressSlot():
            return _address_value(prefix, piece)


def _write(index: int, placed: PlacedPiece) -> tuple[InstructionBase, ...]:
    prefix = f"hlasm.dc.{placed.section}.{placed.offset}.{index}"
    value, value_ir = _value(prefix, placed.piece)
    width, unsigned, image, region, offset = (
        _reg(prefix, role) for role in ("width", "unsigned", "image", "region", "at")
    )
    return (
        *value_ir,
        Const.int_(width, placed.piece.width),
        Const.bool_(unsigned, False),
        CallFunction(
            result_reg=image,
            func_name=INT_TO_BINARY_BYTES,
            args=(value, width, unsigned),
        ),
        LoadVar(result_reg=region, name=section_var(placed.section)),
        Const.int_(offset, placed.offset),
        WriteRegion(
            region_reg=region,
            offset_reg=offset,
            length=placed.piece.width,
            value_reg=image,
        ),
    )


def section_allocation(program: HlasmProgram) -> tuple[InstructionBase, ...]:
    sections = tuple(s for s in program.sections if s.kind != SectionKind.DSECT)
    names = frozenset(section.name for section in sections)
    return (
        *chain.from_iterable(_allocate(section) for section in sections),
        *chain.from_iterable(
            _write(index, placed)
            for index, placed in enumerate(_placed(program, names))
        ),
    )
