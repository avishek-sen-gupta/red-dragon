# pyright: standard
"""Signed-packed-decimal fields in IR at a run-time length: read into a magnitude, a negative bit and bad-digit and bad-sign bits; stored right to left with a preferred sign; signs and bounds are int compares."""

from interpreter.hlasm.byte_loop import emit_byte_loop
from interpreter.hlasm.decimal_exceptions import emit_decimal_overflow_check
from interpreter.hlasm.hlasm_constants import (
    DECIMAL_INVALID_VAR,
    DECIMAL_VALUE_VAR,
    MAKE_LIST,
    NIBBLE_BITS,
    NIBBLE_MASK,
    ONE_BYTE,
    OVERFLOW_CC,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.packed_byte_sink import PackedByteSink
from interpreter.hlasm.packed_digit_reader import PackedDigitReader
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.packed_value import PackedValue
from interpreter.hlasm.unit_value import unit_reader
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

NOT_DIGITS = 0xFC00
NOT_SIGNS = 0x03FF
MINUS_SIGNS = (1 << 0xB) | (1 << 0xD)
PLUS_SIGNS = (1 << 0xA) | (1 << 0xC) | (1 << 0xE) | (1 << 0xF)
PLUS_SIGN = 0xC
DECIMAL_BASE = 10
DIGIT_PAIR_BASE = 100
SIGN_CC_STEP = 2


def _bin(
    emitter: HlasmEmitter, operator: BinopKind, left: Register, right: int
) -> Register:
    return emitter.binop(operator, left, emitter.int_(right))


def table_bit(emitter: HlasmEmitter, table: Register, nibble: Register) -> Register:
    return _bin(
        emitter, BinopKind.BIT_AND, emitter.binop(BinopKind.RSHIFT, table, nibble), 1
    )


def power_of_ten(emitter: HlasmEmitter, exponent: Register) -> Register:
    return emitter.binop(BinopKind.POWER, emitter.int_(DECIMAL_BASE), exponent)


def digit_limit(emitter: HlasmEmitter, length: Register) -> Register:
    doubled = _bin(emitter, BinopKind.MUL, length, 2)
    return power_of_ten(emitter, _bin(emitter, BinopKind.SUB, doubled, 1))


def negative_bit(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.LT, value, emitter.int_(0))


def nonzero_bit(emitter: HlasmEmitter, magnitude: Register) -> Register:
    return emitter.binop(BinopKind.GT, magnitude, emitter.int_(0))


def at_least(emitter: HlasmEmitter, value: Register, bound: Register) -> Register:
    return emitter.binop(BinopKind.GE, value, bound)


def sign_factor(emitter: HlasmEmitter, negative: Register) -> Register:
    doubled = _bin(emitter, BinopKind.MUL, negative, 2)
    return emitter.binop(BinopKind.SUB, emitter.int_(1), doubled)


def signed_value(emitter: HlasmEmitter, value: PackedValue) -> Register:
    return emitter.binop(
        BinopKind.MUL, value.magnitude, sign_factor(emitter, value.negative)
    )


def _nibbles(emitter: HlasmEmitter, byte: Register) -> tuple[Register, Register]:
    high = _bin(emitter, BinopKind.RSHIFT, byte, NIBBLE_BITS)
    return high, _bin(emitter, BinopKind.BIT_AND, byte, NIBBLE_MASK)


def _flag(emitter: HlasmEmitter, bit: Register) -> None:
    invalid = emitter.binop(
        BinopKind.BIT_OR, emitter.load_var(DECIMAL_INVALID_VAR), bit
    )
    emitter.emit_inst(StoreVar(name=DECIMAL_INVALID_VAR, value_reg=invalid))


def _digit_pair(
    emitter: HlasmEmitter,
    site: PackedDigitReader,
    at: Register,
) -> None:
    high, low = _nibbles(emitter, site.read(site.address, at))
    shifted = _bin(
        emitter, BinopKind.MUL, emitter.load_var(DECIMAL_VALUE_VAR), DIGIT_PAIR_BASE
    )
    pair = emitter.binop(
        BinopKind.ADD, _bin(emitter, BinopKind.MUL, high, DECIMAL_BASE), low
    )
    emitter.emit_inst(
        StoreVar(
            name=DECIMAL_VALUE_VAR,
            value_reg=emitter.binop(BinopKind.ADD, shifted, pair),
        )
    )
    _flag(
        emitter,
        emitter.binop(
            BinopKind.BIT_OR,
            table_bit(emitter, site.not_digits, high),
            table_bit(emitter, site.not_digits, low),
        ),
    )


def _sign_byte(
    emitter: HlasmEmitter, site: PackedDigitReader, last: Register
) -> PackedValue:
    high, sign = _nibbles(emitter, site.read(site.address, last))
    shifted = _bin(
        emitter, BinopKind.MUL, emitter.load_var(DECIMAL_VALUE_VAR), DECIMAL_BASE
    )
    _flag(emitter, table_bit(emitter, site.not_digits, high))
    return PackedValue(
        emitter.binop(BinopKind.ADD, shifted, high),
        table_bit(emitter, emitter.int_(MINUS_SIGNS), sign),
        emitter.load_var(DECIMAL_INVALID_VAR),
        table_bit(emitter, emitter.int_(NOT_SIGNS), sign),
    )


def read_packed(emitter: HlasmEmitter, field: PackedField) -> PackedValue:
    emitter.emit_inst(StoreVar(name=DECIMAL_VALUE_VAR, value_reg=emitter.int_(0)))
    emitter.emit_inst(StoreVar(name=DECIMAL_INVALID_VAR, value_reg=emitter.int_(0)))
    site = PackedDigitReader(
        field.address, unit_reader(emitter, ONE_BYTE), emitter.int_(NOT_DIGITS)
    )
    last = _bin(emitter, BinopKind.SUB, field.length, ONE_BYTE)
    emit_byte_loop(emitter, last, lambda at: _digit_pair(emitter, site, at))
    return _sign_byte(emitter, site, last)


def _write_byte(
    emitter: HlasmEmitter,
    sink: PackedByteSink,
    at: Register,
    value: Register,
) -> None:
    image = emitter.call(MAKE_LIST, (sink.single, value))
    emitter.write_bytes(sink.address, at, ONE_BYTE, image)


def _packed_byte(emitter: HlasmEmitter, high: Register, low: Register) -> Register:
    return emitter.binop(
        BinopKind.BIT_OR, _bin(emitter, BinopKind.LSHIFT, high, NIBBLE_BITS), low
    )


def _store_pair(
    emitter: HlasmEmitter, sink: PackedByteSink, last: Register, at: Register
) -> None:
    remaining = emitter.load_var(DECIMAL_VALUE_VAR)
    low = _bin(emitter, BinopKind.MOD, remaining, DECIMAL_BASE)
    tens = _bin(emitter, BinopKind.FLOOR_DIV, remaining, DECIMAL_BASE)
    high = _bin(emitter, BinopKind.MOD, tens, DECIMAL_BASE)
    offset = _bin(
        emitter, BinopKind.SUB, emitter.binop(BinopKind.SUB, last, at), ONE_BYTE
    )
    _write_byte(emitter, sink, offset, _packed_byte(emitter, high, low))
    rest = _bin(emitter, BinopKind.FLOOR_DIV, remaining, DIGIT_PAIR_BASE)
    emitter.emit_inst(StoreVar(name=DECIMAL_VALUE_VAR, value_reg=rest))


def store_packed(
    emitter: HlasmEmitter, field: PackedField, magnitude: Register, negative: Register
) -> None:
    sink = PackedByteSink(field.address, emitter.int_(ONE_BYTE))
    last = _bin(emitter, BinopKind.SUB, field.length, ONE_BYTE)
    units = _bin(emitter, BinopKind.MOD, magnitude, DECIMAL_BASE)
    sign = _bin(emitter, BinopKind.BIT_OR, negative, PLUS_SIGN)
    _write_byte(emitter, sink, last, _packed_byte(emitter, units, sign))
    rest = _bin(emitter, BinopKind.FLOOR_DIV, magnitude, DECIMAL_BASE)
    emitter.emit_inst(StoreVar(name=DECIMAL_VALUE_VAR, value_reg=rest))
    emit_byte_loop(emitter, last, lambda at: _store_pair(emitter, sink, last, at))


def _result_cc(
    emitter: HlasmEmitter, magnitude: Register, negative: Register, overflow: Register
) -> Register:
    sign_cc = emitter.binop(BinopKind.SUB, emitter.int_(SIGN_CC_STEP), negative)
    base = emitter.binop(BinopKind.MUL, nonzero_bit(emitter, magnitude), sign_cc)
    lift = emitter.binop(
        BinopKind.MUL,
        emitter.binop(BinopKind.SUB, emitter.int_(OVERFLOW_CC), base),
        overflow,
    )
    return emitter.binop(BinopKind.ADD, base, lift)


def store_with_cc(
    emitter: HlasmEmitter, field: PackedField, magnitude: Register, negative: Register
) -> None:
    limit = digit_limit(emitter, field.length)
    overflow = at_least(emitter, magnitude, limit)
    kept = emitter.binop(BinopKind.MOD, magnitude, limit)
    store_packed(emitter, field, kept, negative)
    emitter.set_cc(_result_cc(emitter, magnitude, negative, overflow))
    emit_decimal_overflow_check(emitter, overflow)


def store_signed(emitter: HlasmEmitter, field: PackedField, value: Register) -> None:
    negative = negative_bit(emitter, value)
    magnitude = emitter.binop(BinopKind.MUL, value, sign_factor(emitter, negative))
    store_with_cc(emitter, field, magnitude, negative)
