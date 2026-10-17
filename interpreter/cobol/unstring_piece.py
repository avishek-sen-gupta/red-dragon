"""What one UNSTRING receiver is given: its characters, the delimiter that
ended them (empty at the end of the source) and the count examined."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnstringPiece:
    text: str
    delimiter: str
    count: int
