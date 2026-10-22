# pyright: standard
"""A field of an instruction's byte 1: its bit position and width, and the operand it encodes."""

from dataclasses import dataclass

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_part import ByteOnePart


@dataclass(frozen=True)
class ByteOneField:
    shift: int
    width: int
    operand: int
    part: ByteOnePart

    @property
    def bits(self) -> int:
        return ((1 << self.width) - 1) << self.shift

    def placed(self, statement: MachineStatement) -> int:
        return (self.part.code(statement, self.operand) << self.shift) & self.bits

    def rewritten(self, statement: MachineStatement, byte: int) -> MachineStatement:
        code = (byte & self.bits) >> self.shift
        operands = statement.operands
        replaced = (
            *operands[: self.operand],
            self.part.coded(statement, self.operand, code),
            *operands[self.operand + 1 :],
        )
        return statement.model_copy(update={"operands": replaced})
