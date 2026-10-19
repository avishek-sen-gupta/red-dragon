# pyright: standard
"""An ALTERNATE RECORD KEY clause: the key data item, and whether its values may repeat."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class AlternateRecordKey:
    key: RefModOperand
    duplicates: bool

    @classmethod
    def from_dict(cls, data: Mapping) -> AlternateRecordKey:
        return cls(RefModOperand.from_dict(data["key"]), data["duplicates"])

    def to_dict(self) -> dict:
        return {"key": self.key.to_dict(), "duplicates": self.duplicates}
