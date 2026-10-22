# pyright: standard
"""Storage compares: CLC, the long compares, COMPARE LOGICAL STRING and COMPARE UNTIL SUBSTRING EQUAL; storage is never written."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import LENGTH_BYTE
from interpreter.hlasm.compare_string import compare_string
from interpreter.hlasm.compare_substring import COMPARE_UNTIL_SUBSTRING_EQUAL
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.fixed_width_ir import build_compare_logical_cc_ir
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    MAX_FIELD_BYTES,
    PARAM_LEFT,
    PARAM_RIGHT,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.long_compare import (
    COMPARE_LONG,
    COMPARE_LONG_EXTENDED,
    COMPARE_LONG_UNICODE,
)
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering

FIELD_BITS = BITS_PER_BYTE * MAX_FIELD_BYTES
FIELD_COMPARISON = build_compare_logical_cc_ir(f"hlasm.cmpl{FIELD_BITS}", FIELD_BITS)


def _compare_characters(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    first_address = length_operand_address(
        emitter, storage_length_operand(statement, FIRST_OPERAND)
    )
    second_address = effective_address(
        emitter, storage_operand(statement, SECOND_OPERAND)
    )
    length = field.length(emitter)
    values = {
        PARAM_LEFT: length.loaded(emitter, first_address),
        PARAM_RIGHT: length.loaded(emitter, second_address),
    }
    emitter.set_cc(inline_ir(emitter, FIELD_COMPARISON, values))


SS_COMPARE_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "CLC": FieldLowering(LENGTH_BYTE, _compare_characters),
}

SS_COMPARE_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(SS_COMPARE_FIELD_LOWERINGS),
    "CLCL": COMPARE_LONG,
    "CLCLE": COMPARE_LONG_EXTENDED,
    "CLCLU": COMPARE_LONG_UNICODE,
    "CLST": compare_string,
    "CUSE": COMPARE_UNTIL_SUBSTRING_EQUAL,
}
