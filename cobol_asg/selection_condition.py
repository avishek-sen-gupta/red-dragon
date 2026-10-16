"""SelectionCondition — a condition as an EVALUATE subject or as a WHEN object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectionCondition:
    condition: dict

    def to_dict(self) -> dict:
        return {"kind": "condition", "condition": self.condition}
