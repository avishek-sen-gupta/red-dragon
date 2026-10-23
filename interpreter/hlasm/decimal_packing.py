# pyright: standard
"""Packing digits into a signed-packed field and unpacking them into characters, right to left one result unit at a time, each source byte fetched once, just before the first unit it feeds is stored; source bytes left of the operand read as zero."""

from collections.abc import Callable

from interpreter.hlasm.byte_loop import emit_counted_loop
from interpreter.hlasm.character_field import CharacterField
from interpreter.hlasm.conditional import emit_when, pick
from interpreter.hlasm.digit_source import DigitSource
from interpreter.hlasm.hlasm_constants import (
    ONE_BYTE,
    UNPACK_BYTE_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.packed_decimal import constant_binop, nibbles, packed_byte
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type SignOf = Callable[[Register], Register]

DIGITS_PER_BYTE = 2


def _low(emitter: HlasmEmitter, byte: Register) -> Register:
    return nibbles(emitter, byte)[1]


def _byte_or_zero(
    emitter: HlasmEmitter, read: UnitReader, address: Register, offset: Register
) -> Register:
    present = constant_binop(emitter, BinopKind.GE, offset, 0)
    at = emitter.binop(BinopKind.MUL, offset, present)
    return emitter.binop(BinopKind.MUL, read(address, at), present)


def _write(
    emitter: HlasmEmitter, address: Register, at: Register, value: Register, width: int
) -> None:
    emitter.write_bytes(address, at, width, emitter.image(value, width))


def _digit(
    emitter: HlasmEmitter, source: DigitSource, read: UnitReader, index: Register
) -> Register:
    back = constant_binop(emitter, BinopKind.MUL, index, source.stride)
    offset = emitter.binop(BinopKind.SUB, source.last, back)
    return _low(emitter, _byte_or_zero(emitter, read, source.address, offset))


def _pair(
    emitter: HlasmEmitter,
    target: PackedField,
    source: tuple[DigitSource, UnitReader],
    at: Register,
) -> None:
    digits, read = source
    high_index = constant_binop(emitter, BinopKind.MUL, at, DIGITS_PER_BYTE)
    low_index = constant_binop(emitter, BinopKind.SUB, high_index, 1)
    low = _digit(emitter, digits, read, low_index)
    high = _digit(emitter, digits, read, high_index)
    last = constant_binop(emitter, BinopKind.SUB, target.length, ONE_BYTE)
    offset = emitter.binop(BinopKind.SUB, last, at)
    _write(emitter, target.address, offset, packed_byte(emitter, high, low), ONE_BYTE)


def emit_pack(
    emitter: HlasmEmitter, target: PackedField, source: DigitSource, sign: SignOf
) -> None:
    read = unit_reader(emitter, ONE_BYTE)
    rightmost = read(source.address, source.last)
    last = constant_binop(emitter, BinopKind.SUB, target.length, ONE_BYTE)
    signed = packed_byte(emitter, _low(emitter, rightmost), sign(rightmost))
    _write(emitter, target.address, last, signed, ONE_BYTE)
    span = (emitter.int_(1), target.length)
    emit_counted_loop(
        emitter, span, ONE_BYTE, lambda at: _pair(emitter, target, (source, read), at)
    )


def _write_unit(
    emitter: HlasmEmitter, target: CharacterField, at: Register, value: Register
) -> None:
    after = constant_binop(emitter, BinopKind.ADD, at, 1)
    back = constant_binop(emitter, BinopKind.MUL, after, target.width)
    offset = emitter.binop(BinopKind.SUB, target.length, back)
    _write(emitter, target.address, offset, value, target.width)


def _fetched(
    emitter: HlasmEmitter, source: tuple[PackedField, UnitReader], at: Register
) -> Register:
    field, read = source
    pairs = constant_binop(
        emitter, BinopKind.RSHIFT, constant_binop(emitter, BinopKind.ADD, at, 1), 1
    )
    last = constant_binop(emitter, BinopKind.SUB, field.length, ONE_BYTE)
    offset = emitter.binop(BinopKind.SUB, last, pairs)
    return _byte_or_zero(emitter, read, field.address, offset)


def _unit(
    emitter: HlasmEmitter,
    target: CharacterField,
    source: tuple[PackedField, UnitReader],
    at: Register,
) -> None:
    odd = constant_binop(emitter, BinopKind.BIT_AND, at, 1)
    emit_when(
        emitter,
        odd,
        lambda: emitter.store_var(UNPACK_BYTE_VAR, _fetched(emitter, source, at)),
    )
    high, low = nibbles(emitter, emitter.load_var(UNPACK_BYTE_VAR))
    zoned = constant_binop(
        emitter, BinopKind.BIT_OR, pick(emitter, odd, low, high), target.zone
    )
    _write_unit(emitter, target, at, zoned)


def emit_unpack(
    emitter: HlasmEmitter,
    target: CharacterField,
    source: PackedField,
    first_zone: SignOf,
) -> Register:
    read = unit_reader(emitter, ONE_BYTE)
    last = constant_binop(emitter, BinopKind.SUB, source.length, ONE_BYTE)
    rightmost = read(source.address, last)
    first = emitter.binop(
        BinopKind.BIT_OR, first_zone(rightmost), nibbles(emitter, rightmost)[0]
    )
    _write_unit(emitter, target, emitter.int_(0), first)
    units = constant_binop(emitter, BinopKind.FLOOR_DIV, target.length, target.width)
    span = (emitter.int_(1), units)
    emit_counted_loop(
        emitter, span, ONE_BYTE, lambda at: _unit(emitter, target, (source, read), at)
    )
    return _low(emitter, rightmost)
