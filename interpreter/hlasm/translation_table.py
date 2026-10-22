# pyright: standard
"""The translates' tables: a byte translated through a 256-byte table, the GR1 table address with bits 61-63 ignored, and offsets rescaled between unit widths; constants are set before any loop."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    DOUBLEWORD_BYTES,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Rescale = Callable[[Register], Register]

TABLE_REGISTER = 1
DOUBLEWORD_TABLE_MASK = ADDRESS_MASK_31 & ~(DOUBLEWORD_BYTES - 1)
HALVE_OR_DOUBLE = 1


def translate_byte(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    argument: Register,
    at: Register,
) -> None:
    target, table = addresses
    function = emitter.load_bytes(table, argument, ONE_BYTE)
    emitter.write_bytes(target, at, ONE_BYTE, function)


def table_address(emitter: HlasmEmitter) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(TABLE_REGISTER),
        emitter.int_(DOUBLEWORD_TABLE_MASK),
    )


def rescale(emitter: HlasmEmitter, widths: tuple[int, int]) -> Rescale:
    source, target = widths
    if source == target:
        return lambda offset: offset
    shift = emitter.int_(HALVE_OR_DOUBLE)
    operator = BinopKind.LSHIFT if target > source else BinopKind.RSHIFT
    return lambda offset: emitter.binop(operator, offset, shift)
