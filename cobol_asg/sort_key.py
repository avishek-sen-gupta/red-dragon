"""One SORT or MERGE key: the data item and the direction it orders records in."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand
from cobol_asg.sort_key_direction import SortKeyDirection


@dataclass(frozen=True)
class SortKey:
    direction: SortKeyDirection
    key: RefModOperand

    @classmethod
    def from_dict(cls, data: Mapping) -> SortKey:
        return cls(
            direction=SortKeyDirection(data["direction"]),
            key=RefModOperand.from_dict(data["key"]),
        )

    def to_dict(self) -> dict:
        return {"direction": self.direction.value, "key": self.key.to_dict()}
