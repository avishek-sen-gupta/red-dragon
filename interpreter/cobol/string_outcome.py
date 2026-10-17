"""What a STRING statement leaves: the receiver's characters, the pointer, and
whether the overflow condition arose."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StringOutcome:
    image: str
    pointer: int
    overflow: bool
