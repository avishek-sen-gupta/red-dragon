# pyright: standard
"""Byte 1 of an instruction format: the operand fields, the bits ignored, and the rest, which are opcode."""

from dataclasses import dataclass
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_field import ByteOneField
from interpreter.hlasm.hlasm_constants import BYTE_MASK


@dataclass(frozen=True)
class ByteOneLayout:
    fields: tuple[ByteOneField, ...]
    ignored_bits: int

    @property
    def field_bits(self) -> int:
        return reduce(lambda bits, f: bits | f.bits, self.fields, 0)

    @property
    def opcode_bits(self) -> int:
        return BYTE_MASK & ~(self.field_bits | self.ignored_bits)

    def byte_of(self, statement: MachineStatement) -> int:
        return reduce(lambda byte, f: byte | f.placed(statement), self.fields, 0)

    def reachable(self, statement: MachineStatement) -> tuple[int, ...]:
        original = self.byte_of(statement)
        return tuple(
            v
            for v in range(BYTE_MASK + 1)
            if v & self.field_bits == v and v & original == original
        )

    def variant(self, statement: MachineStatement, byte: int) -> MachineStatement:
        return reduce(lambda s, f: f.rewritten(s, byte), self.fields, statement)
