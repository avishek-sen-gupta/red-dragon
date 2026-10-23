# pyright: standard
"""Lowers one assembled statement; data statements were laid out at start-up."""

import logging

from hlasm_asg.program.ccw_statement import CcwStatement
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.ds_statement import DsStatement
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.statement import Statement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.execute import EXECUTE_MNEMONICS, lower_execute
from interpreter.hlasm.hlasm_constants import OPERATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine_statements import MachineStatements
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS

logger = logging.getLogger(__name__)


def _unsupported(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    logger.warning(
        "HLASM opcode %s has no lowering; it abends %s",
        statement.base_mnemonic,
        OPERATION_EXCEPTION_ABEND,
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


def lower_machine(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    OPCODE_LOWERINGS.get(statement.base_mnemonic, _unsupported)(emitter, statement)


def _lower_instruction(
    emitter: HlasmEmitter, statement: MachineStatement, statements: MachineStatements
) -> None:
    if statement.base_mnemonic in EXECUTE_MNEMONICS:
        lower_execute(emitter, statement, statements, lower_machine)
        return
    lower_machine(emitter, statement)


def lower_statement(
    emitter: HlasmEmitter, statement: Statement, statements: MachineStatements
) -> None:
    match statement:
        case MachineStatement():
            _lower_instruction(emitter, statement, statements)
        case DcStatement() | DsStatement() | CcwStatement():
            return
