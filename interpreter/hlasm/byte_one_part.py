# pyright: standard
"""How one byte-1 field of an executed instruction reads from and writes into its operand."""

from typing import Protocol

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand


class ByteOnePart(Protocol):
    def code(self, statement: MachineStatement, index: int) -> int: ...

    def coded(self, statement: MachineStatement, index: int, code: int) -> Operand: ...
