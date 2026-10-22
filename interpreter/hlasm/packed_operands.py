# pyright: standard
"""The packed-decimal storage operands: D1(L1,B1) and, in SS-b, D2(L2,B2), as fields whose lengths come from byte 1's nibbles; both read and checked together."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import length_operand_address
from interpreter.hlasm.hlasm_constants import NIBBLE_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import storage_length_operand
from interpreter.hlasm.packed_decimal import read_packed
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.packed_value import PackedValue
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FIRST_FIELD = (NIBBLE_BITS, NIBBLE_BITS)
SECOND_FIELD = (0, NIBBLE_BITS)

type PackedFields = tuple[PackedField, PackedField]
type PackedValues = tuple[PackedValue, PackedValue]


def _length(emitter: HlasmEmitter, field: DataField, part: tuple[int, int]) -> Register:
    return field.part(emitter, *part).length(emitter).value(emitter)


def first_field(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> PackedField:
    first = storage_length_operand(statement, FIRST_OPERAND)
    return PackedField(
        length_operand_address(emitter, first), _length(emitter, field, FIRST_FIELD)
    )


def packed_fields(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> PackedFields:
    second = storage_length_operand(statement, SECOND_OPERAND)
    return first_field(emitter, statement, field), PackedField(
        length_operand_address(emitter, second),
        _length(emitter, field, SECOND_FIELD),
    )


def read_both(emitter: HlasmEmitter, fields: PackedFields) -> PackedValues:
    first, second = (read_packed(emitter, f) for f in fields)
    return first, second


def either_invalid(emitter: HlasmEmitter, values: PackedValues) -> Register:
    first, second = values
    return emitter.binop(
        BinopKind.BIT_OR, first.invalid(emitter), second.invalid(emitter)
    )
