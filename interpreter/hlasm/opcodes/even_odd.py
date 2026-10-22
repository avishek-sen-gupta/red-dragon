# pyright: standard
"""An instruction on an even-odd register pair whose R1 is odd is a specification exception: the run abends S0C6 before any register is read."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.data_movement import REGISTER_OPERAND
from interpreter.hlasm.hlasm_constants import SPECIFICATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering


def even_odd(lowering: StatementLowering) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if reg_operand(statement, REGISTER_OPERAND) % 2:
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement)

    return lower
