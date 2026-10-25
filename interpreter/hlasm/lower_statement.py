# pyright: standard
"""Lowers one assembled statement: an instruction, or a label at each CNOP padding halfword; data statements were laid out at start-up."""

import logging

from hlasm_asg.program.cnop_statement import CnopStatement
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.statement import Statement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.branch_dispatch import statement_label
from interpreter.hlasm.execute import EXECUTE_MNEMONICS, lower_execute
from interpreter.hlasm.hlasm_constants import OPERATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine_statements import MachineStatements
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import Label_

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


def _label_no_ops(emitter: HlasmEmitter, statement: CnopStatement) -> None:
    _ = [
        emitter.emit_inst(Label_(label=statement_label(statement.section, at)))
        for at in statement.no_ops()[1:]
    ]


def lower_statement(
    emitter: HlasmEmitter, statement: Statement, statements: MachineStatements
) -> None:
    match statement:
        case MachineStatement():
            _lower_instruction(emitter, statement, statements)
        case CnopStatement():
            _label_no_ops(emitter, statement)
