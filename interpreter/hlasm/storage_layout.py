# pyright: standard
"""Each section's constants, literals, CXD fields and CNOP padding as pieces at their offsets: constant images and address and binder slots."""

from collections.abc import Iterable, Sequence
from functools import reduce
from itertools import accumulate, chain, groupby
from operator import itemgetter, or_

from hlasm_asg.program.ccw_statement import CcwStatement
from hlasm_asg.program.cnop_statement import CnopStatement
from hlasm_asg.program.cxd_statement import CxdStatement
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.origin import Origin
from interpreter.hlasm.binder_slot import BinderSlot
from interpreter.hlasm.bit_length_image import BitLengthImage
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import DcPiece, encode_ccw, encode_dc
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, WORD_BYTES
from interpreter.hlasm.placed_piece import PlacedPiece
from interpreter.project.no_relocation_target import NoRelocationTarget
from interpreter.project.relocation_kind import RelocationKind

_TOTAL = BinderSlot(RelocationKind.PR_TOTAL, NoRelocationTarget(), WORD_BYTES)
_NO_OP = ConstantImage((0x07, 0x00))

type ByteAt = tuple[int, int]


def _place_pieces(
    section: str, start: int, pieces: tuple[DcPiece, ...]
) -> tuple[PlacedPiece, ...]:
    offsets = accumulate((piece.width for piece in pieces), initial=start)
    return tuple(
        PlacedPiece(section, offset, piece)
        for offset, piece in zip(offsets, pieces, strict=False)
    )


def _field_bytes(start: int, bits: int, value: int) -> tuple[ByteAt, ...]:
    first = start // BITS_PER_BYTE
    end = -(-(start + bits) // BITS_PER_BYTE)
    shifted = value << (end * BITS_PER_BYTE - start - bits)
    return tuple(
        zip(range(first, end), shifted.to_bytes(end - first, "big"), strict=True)
    )


def _image_bytes(item: DcItem, image: BitLengthImage) -> tuple[ByteAt, ...]:
    start = item.offset * BITS_PER_BYTE + item.bit_offset
    return tuple(
        chain.from_iterable(
            _field_bytes(start + index * image.bits, image.bits, value)
            for index, value in enumerate(image.values)
        )
    )


def _packed_bytes(
    section: str, contributions: Iterable[ByteAt]
) -> tuple[PlacedPiece, ...]:
    return tuple(
        PlacedPiece(
            section, offset, ConstantImage((reduce(or_, (b for _, b in group)),))
        )
        for offset, group in groupby(sorted(contributions), itemgetter(0))
    )


def _place_items(
    section: str, items: Sequence[DcItem], origin: Origin
) -> tuple[PlacedPiece, ...]:
    encoded = tuple((item, encode_dc(item, origin)) for item in items)
    bits = chain.from_iterable(
        _image_bytes(item, image)
        for item, image in encoded
        if isinstance(image, BitLengthImage)
    )
    pieces = chain.from_iterable(
        _place_pieces(section, item.offset, image)
        for item, image in encoded
        if not isinstance(image, BitLengthImage)
    )
    return (*pieces, *_packed_bytes(section, bits))


def placed_pieces(
    program: HlasmProgram, sections: frozenset[str]
) -> tuple[PlacedPiece, ...]:
    statements = (
        _place_items(s.section, s.items, s.origin)
        for s in program.statements
        if isinstance(s, DcStatement) and s.section in sections
    )
    literals = (
        _place_items(literal.section, (literal.item,), literal.origin)
        for literal in program.literals
        if literal.section in sections
    )
    channel_commands = (
        _place_pieces(s.section, s.offset, encode_ccw(s))
        for s in program.statements
        if isinstance(s, CcwStatement) and s.section in sections
    )
    totals = (
        _place_pieces(s.section, s.offset, (_TOTAL,))
        for s in program.statements
        if isinstance(s, CxdStatement) and s.section in sections
    )
    padding = (
        _place_pieces(s.section, s.offset, tuple(_NO_OP for _ in s.no_ops()))
        for s in program.statements
        if isinstance(s, CnopStatement) and s.section in sections
    )
    return tuple(
        chain.from_iterable(
            chain(statements, literals, channel_commands, totals, padding)
        )
    )
