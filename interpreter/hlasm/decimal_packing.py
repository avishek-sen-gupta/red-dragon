# pyright: standard
"""Packing digits into a signed-packed field and unpacking them into characters, right to left one result unit at a time, each unit's source bytes fetched just before it is stored; source bytes left of the operand read as zero."""

from collections.abc import Callable

from interpreter.hlasm.byte_loop import emit_counted_loop
from interpreter.hlasm.character_field import CharacterField
from interpreter.hlasm.digit_source import DigitSource
from interpreter.hlasm.hlasm_constants import (
    NIBBLE_BITS,
    NIBBLE_MASK,
    ONE_BYTE,
    UNPACK_CARRY_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type SignOf = Callable[[Register], Register]

DIGITS_PER_BYTE = 2


def _bin(
    emitter: HlasmEmitter, operator: BinopKind, left: Register, right: int
) -> Register:
    return emitter.binop(operator, left, emitter.int_(right))


def _low(emitter: HlasmEmitter, byte: Register) -> Register:
    return _bin(emitter, BinopKind.BIT_AND, byte, NIBBLE_MASK)


def _high(emitter: HlasmEmitter, byte: Register) -> Register:
    return _bin(emitter, BinopKind.RSHIFT, byte, NIBBLE_BITS)


def _joined(emitter: HlasmEmitter, high: Register, low: Register) -> Register:
    shifted = _bin(emitter, BinopKind.LSHIFT, high, NIBBLE_BITS)
    return emitter.binop(BinopKind.BIT_OR, shifted, low)


def _byte_or_zero(
    emitter: HlasmEmitter, read: UnitReader, address: Register, offset: Register
) -> Register:
    present = _bin(emitter, BinopKind.GE, offset, 0)
    at = emitter.binop(BinopKind.MUL, offset, present)
    return emitter.binop(BinopKind.MUL, read(address, at), present)


def _write(
    emitter: HlasmEmitter, address: Register, at: Register, value: Register, width: int
) -> None:
    emitter.write_bytes(address, at, width, emitter.image(value, width))


def _digit(
    emitter: HlasmEmitter, source: DigitSource, read: UnitReader, index: Register
) -> Register:
    back = _bin(emitter, BinopKind.MUL, index, source.stride)
    offset = emitter.binop(BinopKind.SUB, source.last, back)
    return _low(emitter, _byte_or_zero(emitter, read, source.address, offset))


def _pair(
    emitter: HlasmEmitter,
    target: PackedField,
    source: tuple[DigitSource, UnitReader],
    at: Register,
) -> None:
    digits, read = source
    high_index = _bin(emitter, BinopKind.MUL, at, DIGITS_PER_BYTE)
    low_index = _bin(emitter, BinopKind.SUB, high_index, 1)
    low = _digit(emitter, digits, read, low_index)
    high = _digit(emitter, digits, read, high_index)
    last = _bin(emitter, BinopKind.SUB, target.length, ONE_BYTE)
    offset = emitter.binop(BinopKind.SUB, last, at)
    _write(emitter, target.address, offset, _joined(emitter, high, low), ONE_BYTE)


def emit_pack(
    emitter: HlasmEmitter, target: PackedField, source: DigitSource, sign: SignOf
) -> None:
    read = unit_reader(emitter, ONE_BYTE)
    rightmost = read(source.address, source.last)
    last = _bin(emitter, BinopKind.SUB, target.length, ONE_BYTE)
    signed = _joined(emitter, _low(emitter, rightmost), sign(rightmost))
    _write(emitter, target.address, last, signed, ONE_BYTE)
    span = (emitter.int_(1), target.length)
    emit_counted_loop(
        emitter, span, ONE_BYTE, lambda at: _pair(emitter, target, (source, read), at)
    )


def _chosen(
    emitter: HlasmEmitter, odd: Register, fetched: Register, kept: Register
) -> Register:
    change = emitter.binop(BinopKind.SUB, fetched, kept)
    return emitter.binop(BinopKind.ADD, kept, emitter.binop(BinopKind.MUL, odd, change))


def _write_unit(
    emitter: HlasmEmitter, target: CharacterField, at: Register, value: Register
) -> None:
    after = _bin(emitter, BinopKind.ADD, at, 1)
    back = _bin(emitter, BinopKind.MUL, after, target.width)
    offset = emitter.binop(BinopKind.SUB, target.length, back)
    _write(emitter, target.address, offset, value, target.width)


def _fetched(
    emitter: HlasmEmitter, source: tuple[PackedField, UnitReader], at: Register
) -> Register:
    field, read = source
    pairs = _bin(emitter, BinopKind.RSHIFT, _bin(emitter, BinopKind.ADD, at, 1), 1)
    last = _bin(emitter, BinopKind.SUB, field.length, ONE_BYTE)
    offset = emitter.binop(BinopKind.SUB, last, pairs)
    return _byte_or_zero(emitter, read, field.address, offset)


def _unit(
    emitter: HlasmEmitter,
    target: CharacterField,
    source: tuple[PackedField, UnitReader],
    at: Register,
) -> None:
    odd = _bin(emitter, BinopKind.BIT_AND, at, 1)
    fetched = _fetched(emitter, source, at)
    kept = emitter.load_var(UNPACK_CARRY_VAR)
    digit = _chosen(emitter, odd, _low(emitter, fetched), kept)
    carry = _chosen(emitter, odd, _high(emitter, fetched), kept)
    emitter.emit_inst(StoreVar(name=UNPACK_CARRY_VAR, value_reg=carry))
    zoned = _bin(emitter, BinopKind.BIT_OR, digit, target.zone)
    _write_unit(emitter, target, at, zoned)


def emit_unpack(
    emitter: HlasmEmitter,
    target: CharacterField,
    source: PackedField,
    first_zone: SignOf,
) -> Register:
    read = unit_reader(emitter, ONE_BYTE)
    last = _bin(emitter, BinopKind.SUB, source.length, ONE_BYTE)
    rightmost = read(source.address, last)
    first = emitter.binop(
        BinopKind.BIT_OR, first_zone(rightmost), _high(emitter, rightmost)
    )
    _write_unit(emitter, target, emitter.int_(0), first)
    emitter.emit_inst(StoreVar(name=UNPACK_CARRY_VAR, value_reg=emitter.int_(0)))
    units = _bin(emitter, BinopKind.FLOOR_DIV, target.length, target.width)
    span = (emitter.int_(1), units)
    emit_counted_loop(
        emitter, span, ONE_BYTE, lambda at: _unit(emitter, target, (source, read), at)
    )
    return _low(emitter, rightmost)
