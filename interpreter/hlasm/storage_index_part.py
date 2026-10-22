# pyright: standard
"""A byte-1 field holding a D(X,B) operand's index register."""

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from interpreter.hlasm.byte_one_part import ByteOnePart
from interpreter.hlasm.operands import storage_operand


class StorageIndex(ByteOnePart):
    def code(self, statement: MachineStatement, index: int) -> int:
        return storage_operand(statement, index).index

    def coded(self, statement: MachineStatement, index: int, code: int) -> Operand:
        return storage_operand(statement, index).model_copy(update={"index": code})
