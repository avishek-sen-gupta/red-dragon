# pyright: standard
"""Lowers one assembled statement; data statements were laid out at start-up."""

import logging

from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.ds_statement import DsStatement
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.statement import Statement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import OPERATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS

logger = logging.getLogger(__name__)


def _unsupported(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    logger.warning(
        "HLASM opcode %s has no lowering; it abends %s",
        statement.base_mnemonic,
        OPERATION_EXCEPTION_ABEND,
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


def lower_statement(emitter: HlasmEmitter, statement: Statement) -> None:
    match statement:
        case MachineStatement():
            OPCODE_LOWERINGS.get(statement.base_mnemonic, _unsupported)(
                emitter, statement
            )
        case DcStatement() | DsStatement():
            return
