# pyright: standard
"""Storage compares: CLC, the long compares, COMPARE LOGICAL STRING and COMPARE UNTIL SUBSTRING EQUAL; storage is never written."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.compare_string import compare_string
from interpreter.hlasm.compare_substring import COMPARE_UNTIL_SUBSTRING_EQUAL
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.fixed_width_ir import build_compare_logical_cc_ir
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    ONE_BYTE,
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


def _compare_characters(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    first = storage_length_operand(statement, FIRST_OPERAND)
    length = max(first.length, ONE_BYTE)
    bits = BITS_PER_BYTE * length
    first_address = length_operand_address(emitter, first)
    second_address = effective_address(
        emitter, storage_operand(statement, SECOND_OPERAND)
    )
    values = {
        PARAM_LEFT: emitter.load_storage(first_address, 0, length),
        PARAM_RIGHT: emitter.load_storage(second_address, 0, length),
    }
    comparison = build_compare_logical_cc_ir(f"hlasm.cmpl{bits}", bits)
    emitter.set_cc(inline_ir(emitter, comparison, values))


SS_COMPARE_LOWERINGS: Mapping[str, StatementLowering] = {
    "CLC": _compare_characters,
    "CLCL": COMPARE_LONG,
    "CLCLE": COMPARE_LONG_EXTENDED,
    "CLCLU": COMPARE_LONG_UNICODE,
    "CLST": compare_string,
    "CUSE": COMPARE_UNTIL_SUBSTRING_EQUAL,
}
