"""The OCCURS DEPENDING ON table at the end of a variable-length item."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OdoTail:
    """Object name, occurrence size and maximum count of an item's ODO table."""

    object_name: str = ""
    element_size: int = 0
    max_count: int = 0

    def is_present(self) -> bool:
        return bool(self.object_name)


NO_ODO_TAIL = OdoTail()
