# pyright: standard
"""SVC: the supervisor calls lowered in IR, by number; any other number abends S0C1."""

import logging
from collections.abc import Callable, Mapping

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.abend_completion import emit_abend_completion
from interpreter.hlasm.hlasm_constants import (
    ABEND_SVC,
    OPERATION_EXCEPTION_ABEND,
    WTO_SVC,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.write_to_operator import emit_write_to_operator

logger = logging.getLogger(__name__)

_SERVICES: Mapping[int, Callable[[HlasmEmitter], None]] = {
    WTO_SVC: emit_write_to_operator,
    ABEND_SVC: emit_abend_completion,
}


def _number(statement: MachineStatement) -> int:
    operand = statement.operands[0]
    assert isinstance(operand, ImmOperand)
    return operand.value


def lower_svc(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    number = _number(statement)
    if number in _SERVICES:
        _SERVICES[number](emitter)
        return
    logger.warning(
        "SVC %d has no lowering; it abends %s", number, OPERATION_EXCEPTION_ABEND
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


SVC_LOWERINGS: Mapping[str, StatementLowering] = {"SVC": lower_svc}
