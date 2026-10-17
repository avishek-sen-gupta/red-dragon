"""The OCCURS DEPENDING ON table at the end of a variable-length item."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_field import NO_ODO_OBJECT
from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class OdoTail:
    """Object reference, occurrence size and maximum count of an item's ODO table."""

    depending_on: RefModOperand = NO_ODO_OBJECT
    element_size: int = 0
    max_count: int = 0

    def is_present(self) -> bool:
        return bool(self.depending_on.name)


NO_ODO_TAIL = OdoTail()
