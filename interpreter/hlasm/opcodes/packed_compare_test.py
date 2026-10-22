# pyright: standard
"""Packed-decimal compare and test: CP checks both operands, then sets the CC from their signed values; TP sets the CC from which of its digits and sign are valid. Neither stores."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import LENGTH_HIGH_NIBBLE, LENGTH_NIBBLES
from interpreter.hlasm.compare_cc import FIRST_HIGH_CC
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.decimal_exceptions import emit_data_check
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.packed_decimal import read_packed, signed_value
from interpreter.hlasm.packed_operands import (
    either_invalid,
    first_field,
    packed_fields,
    read_both,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind

BAD_DIGITS_CC = 2


def _compare(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    values = read_both(emitter, packed_fields(emitter, statement, field))
    emit_data_check(emitter, either_invalid(emitter, values))
    first, second = (signed_value(emitter, v) for v in values)
    low = emitter.binop(BinopKind.LT, first, second)
    high = emitter.binop(BinopKind.GT, first, second)
    emitter.set_cc(
        emitter.binop(
            BinopKind.ADD,
            low,
            emitter.binop(BinopKind.MUL, high, emitter.int_(FIRST_HIGH_CC)),
        )
    )


def _test(emitter: HlasmEmitter, statement: MachineStatement, field: DataField) -> None:
    value = read_packed(emitter, first_field(emitter, statement, field))
    digits = emitter.binop(BinopKind.MUL, value.bad_digits, emitter.int_(BAD_DIGITS_CC))
    emitter.set_cc(emitter.binop(BinopKind.ADD, digits, value.bad_sign))


PACKED_COMPARE_TEST_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "CP": FieldLowering(LENGTH_NIBBLES, _compare),
    "TP": FieldLowering(LENGTH_HIGH_NIBBLE, _test),
}

PACKED_COMPARE_TEST_LOWERINGS: Mapping[str, StatementLowering] = written_lowerings(
    PACKED_COMPARE_TEST_FIELD_LOWERINGS
)
