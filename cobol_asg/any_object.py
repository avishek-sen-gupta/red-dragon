"""AnyObject — WHEN ANY: the object every subject value satisfies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnyObject:
    def to_dict(self) -> dict:
        return {"kind": "any"}
