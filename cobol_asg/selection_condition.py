"""SelectionCondition — a condition as an EVALUATE subject or as a WHEN object."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.condition import Condition, condition_to_dict


@dataclass(frozen=True)
class SelectionCondition:
    condition: Condition

    def to_dict(self) -> dict:
        return {"kind": "condition", "condition": condition_to_dict(self.condition)}
