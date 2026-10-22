# pyright: standard
"""A byte-1 field holding a register, mask or immediate operand's value."""

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from interpreter.hlasm.byte_one_part import ByteOnePart
from interpreter.hlasm.operands import value_operand


class OperandValue(ByteOnePart):
    def code(self, statement: MachineStatement, index: int) -> int:
        return value_operand(statement, index).value

    def coded(self, statement: MachineStatement, index: int, code: int) -> Operand:
        return value_operand(statement, index).model_copy(update={"value": code})
