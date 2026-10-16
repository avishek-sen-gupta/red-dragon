"""TruthValue — TRUE or FALSE as an EVALUATE subject or as a WHEN object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TruthValue:
    value: bool

    def to_dict(self) -> dict:
        return {"kind": "boolean", "value": self.value}
