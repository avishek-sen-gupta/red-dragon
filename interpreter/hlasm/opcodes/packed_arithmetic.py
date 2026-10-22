# pyright: standard
"""Packed-decimal arithmetic: AP, SP, ZAP, MP, DP and SRP; every operand is read and checked before the first store, so improperly overlapping operands meet a sign or digit check."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import LENGTH_AND_IMMEDIATE, LENGTH_NIBBLES
from interpreter.hlasm.data_field import DataField, LowerWithField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.decimal_exceptions import (
    emit_data_check,
    emit_decimal_divide_check,
)
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_constants import NIBBLE_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.packed_decimal import (
    DECIMAL_BASE,
    NOT_DIGITS,
    at_least,
    digit_limit,
    nonzero_bit,
    power_of_ten,
    read_packed,
    signed_value,
    store_packed,
    store_signed,
    store_with_cc,
    table_bit,
)
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.packed_value import PackedValue
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FIRST_FIELD = (NIBBLE_BITS, NIBBLE_BITS)
SECOND_FIELD = (0, NIBBLE_BITS)
LONGEST_FACTOR = 8
SHIFT_BITS = 0x3F
RIGHT_SHIFT_BIT = 5
SHIFT_SPAN = 64

type Fields = tuple[PackedField, PackedField]


def _length(emitter: HlasmEmitter, field: DataField, part: tuple[int, int]) -> Register:
    return field.part(emitter, *part).length(emitter).value(emitter)


def _first_field(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> PackedField:
    first = storage_length_operand(statement, FIRST_OPERAND)
    return PackedField(
        length_operand_address(emitter, first), _length(emitter, field, FIRST_FIELD)
    )


def _fields(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> Fields:
    second = storage_length_operand(statement, SECOND_OPERAND)
    return _first_field(emitter, statement, field), PackedField(
        length_operand_address(emitter, second),
        _length(emitter, field, SECOND_FIELD),
    )


def _read_both(
    emitter: HlasmEmitter, fields: Fields
) -> tuple[PackedValue, PackedValue]:
    first, second = (read_packed(emitter, f) for f in fields)
    return first, second


def _either_invalid(
    emitter: HlasmEmitter, values: tuple[PackedValue, PackedValue]
) -> Register:
    first, second = values
    return emitter.binop(BinopKind.BIT_OR, first.invalid, second.invalid)


def _add(sign_of_second: int) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        fields = _fields(emitter, statement, field)
        values = _read_both(emitter, fields)
        emit_data_check(emitter, _either_invalid(emitter, values))
        first, second = (signed_value(emitter, v) for v in values)
        signed_second = emitter.binop(
            BinopKind.MUL, second, emitter.int_(sign_of_second)
        )
        total = emitter.binop(BinopKind.ADD, first, signed_second)
        result, _ = fields
        store_signed(emitter, result, total)

    return lower


def _zero_and_add(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    first, second = _fields(emitter, statement, field)
    value = read_packed(emitter, second)
    emit_data_check(emitter, value.invalid)
    store_signed(emitter, first, signed_value(emitter, value))


def _check_factor_lengths(emitter: HlasmEmitter, fields: Fields) -> Register:
    first, second = (f.length for f in fields)
    too_long = emitter.binop(BinopKind.GT, second, emitter.int_(LONGEST_FACTOR))
    not_shorter = emitter.binop(BinopKind.GE, second, first)
    emit_specification_check(
        emitter, emitter.binop(BinopKind.OR, too_long, not_shorter)
    )
    return emitter.binop(BinopKind.SUB, first, second)


def _either_sign(
    emitter: HlasmEmitter, values: tuple[PackedValue, PackedValue]
) -> Register:
    first, second = values
    return emitter.binop(BinopKind.BIT_XOR, first.negative, second.negative)


def _multiply(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    fields = _fields(emitter, statement, field)
    spare = _check_factor_lengths(emitter, fields)
    values = _read_both(emitter, fields)
    multiplicand, multiplier = values
    crowded = at_least(emitter, multiplicand.magnitude, digit_limit(emitter, spare))
    invalid = emitter.binop(BinopKind.BIT_OR, _either_invalid(emitter, values), crowded)
    emit_data_check(emitter, invalid)
    product = emitter.binop(BinopKind.MUL, multiplicand.magnitude, multiplier.magnitude)
    multiplicand_field, _ = fields
    store_packed(emitter, multiplicand_field, product, _either_sign(emitter, values))


def _check_quotient(
    emitter: HlasmEmitter,
    values: tuple[PackedValue, PackedValue],
    quotient_length: Register,
) -> None:
    dividend, divisor = values
    aligned = emitter.binop(
        BinopKind.MUL, divisor.magnitude, digit_limit(emitter, quotient_length)
    )
    emit_decimal_divide_check(
        emitter, emitter.binop(BinopKind.LE, aligned, dividend.magnitude)
    )


def _store_quotient_and_remainder(
    emitter: HlasmEmitter,
    fields: Fields,
    values: tuple[PackedValue, PackedValue],
    quotient_length: Register,
) -> None:
    dividend, divisor = values
    dividend_field, divisor_field = fields
    quotient = emitter.binop(BinopKind.FLOOR_DIV, dividend.magnitude, divisor.magnitude)
    remainder = emitter.binop(BinopKind.MOD, dividend.magnitude, divisor.magnitude)
    remainder_address = emitter.binop(
        BinopKind.ADD, dividend_field.address, quotient_length
    )
    store_packed(
        emitter,
        PackedField(dividend_field.address, quotient_length),
        quotient,
        _either_sign(emitter, values),
    )
    store_packed(
        emitter,
        PackedField(remainder_address, divisor_field.length),
        remainder,
        dividend.negative,
    )


def _divide(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    fields = _fields(emitter, statement, field)
    quotient_length = _check_factor_lengths(emitter, fields)
    values = _read_both(emitter, fields)
    emit_data_check(emitter, _either_invalid(emitter, values))
    _check_quotient(emitter, values, quotient_length)
    _store_quotient_and_remainder(emitter, fields, values, quotient_length)


def _shift_amounts(
    emitter: HlasmEmitter, statement: MachineStatement
) -> tuple[Register, Register]:
    address = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    raw = emitter.binop(BinopKind.BIT_AND, address, emitter.int_(SHIFT_BITS))
    rightward = emitter.binop(
        BinopKind.BIT_AND,
        emitter.binop(BinopKind.RSHIFT, raw, emitter.int_(RIGHT_SHIFT_BIT)),
        emitter.int_(1),
    )
    leftward = emitter.binop(BinopKind.BIT_XOR, rightward, emitter.int_(1))
    right = emitter.binop(
        BinopKind.MUL,
        emitter.binop(BinopKind.SUB, emitter.int_(SHIFT_SPAN), raw),
        rightward,
    )
    return emitter.binop(BinopKind.MUL, raw, leftward), right


def _shifted(
    emitter: HlasmEmitter,
    magnitude: Register,
    amounts: tuple[Register, Register],
    rounding: Register,
) -> Register:
    left, right = amounts
    ten = emitter.int_(DECIMAL_BASE)
    widened = emitter.binop(
        BinopKind.MUL,
        emitter.binop(BinopKind.MUL, magnitude, power_of_ten(emitter, left)),
        ten,
    )
    scale = power_of_ten(emitter, right)
    added = emitter.binop(
        BinopKind.MUL,
        emitter.binop(BinopKind.MUL, rounding, scale),
        nonzero_bit(emitter, right),
    )
    return emitter.binop(
        BinopKind.FLOOR_DIV,
        emitter.binop(BinopKind.ADD, widened, added),
        emitter.binop(BinopKind.MUL, scale, ten),
    )


def _shift_and_round(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    first = _first_field(emitter, statement, field)
    rounding = field.part(emitter, *SECOND_FIELD).value(emitter)
    value = read_packed(emitter, first)
    bad_rounding = table_bit(emitter, emitter.int_(NOT_DIGITS), rounding)
    emit_data_check(
        emitter, emitter.binop(BinopKind.BIT_OR, value.invalid, bad_rounding)
    )
    amounts = _shift_amounts(emitter, statement)
    magnitude = _shifted(emitter, value.magnitude, amounts, rounding)
    negative = emitter.binop(
        BinopKind.BIT_AND, value.negative, nonzero_bit(emitter, magnitude)
    )
    store_with_cc(emitter, first, magnitude, negative)


PACKED_ARITHMETIC_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "AP": FieldLowering(LENGTH_NIBBLES, _add(1)),
    "SP": FieldLowering(LENGTH_NIBBLES, _add(-1)),
    "ZAP": FieldLowering(LENGTH_NIBBLES, _zero_and_add),
    "MP": FieldLowering(LENGTH_NIBBLES, _multiply),
    "DP": FieldLowering(LENGTH_NIBBLES, _divide),
    "SRP": FieldLowering(LENGTH_AND_IMMEDIATE, _shift_and_round),
}

PACKED_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = written_lowerings(
    PACKED_ARITHMETIC_FIELD_LOWERINGS
)
