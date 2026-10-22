# pyright: standard
"""An assembly's machine statements by section and offset, for instructions that name another statement."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.statement import Statement


class MachineStatements:
    def __init__(self, statements: Sequence[Statement]) -> None:
        self._by_place = {
            (s.section, s.offset): (s,)
            for s in statements
            if isinstance(s, MachineStatement)
        }

    def at(self, section: str, offset: int) -> tuple[MachineStatement, ...]:
        return self._by_place.get((section, offset), ())
