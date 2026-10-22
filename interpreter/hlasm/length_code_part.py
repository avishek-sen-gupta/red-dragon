# pyright: standard
"""A byte-1 field holding a D(L,B) operand's length code, one less than the length written (0 written is code 0)."""

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from interpreter.hlasm.byte_one_part import ByteOnePart
from interpreter.hlasm.operands import storage_length_operand


class LengthCode(ByteOnePart):
    def code(self, statement: MachineStatement, index: int) -> int:
        return max(storage_length_operand(statement, index).length - 1, 0)

    def coded(self, statement: MachineStatement, index: int, code: int) -> Operand:
        return storage_length_operand(statement, index).model_copy(
            update={"length": code + 1}
        )
