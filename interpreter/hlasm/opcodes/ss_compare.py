# pyright: standard
"""Storage compares: CLC, the long compares, COMPARE LOGICAL STRING and COMPARE UNTIL SUBSTRING EQUAL; storage is never written."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import LENGTH_BYTE
from interpreter.hlasm.compare_cc import (
    EQUAL_CC,
    emit_cc_constant,
    emit_unequal_order,
)
from interpreter.hlasm.compare_string import compare_string
from interpreter.hlasm.compare_substring import COMPARE_UNTIL_SUBSTRING_EQUAL
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_compare import (
    COMPARE_LONG,
    COMPARE_LONG_EXTENDED,
    COMPARE_LONG_UNICODE,
)
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


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
    values = (
        length.loaded(emitter, first_address),
        length.loaded(emitter, second_address),
    )
    _set_order_cc(emitter, values)


def _set_order_cc(emitter: HlasmEmitter, values: tuple[Register, Register]) -> None:
    equal, unequal, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_clc_equal", "hl_clc_unequal", "hl_clc_done")
    )
    same = emitter.binop(BinopKind.EQ, *values)
    emitter.emit_inst(BranchIf(cond_reg=same, branch_targets=(equal, unequal)))
    emit_cc_constant(emitter, EQUAL_CC, equal, done)
    emitter.emit_inst(Label_(label=unequal))
    emit_unequal_order(emitter, values, done)
    emitter.emit_inst(Label_(label=done))


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
