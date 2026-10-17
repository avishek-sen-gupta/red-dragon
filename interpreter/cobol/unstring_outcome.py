"""What an UNSTRING statement leaves: one piece per receiver acted on, the
pointer, and whether the overflow condition arose."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.unstring_piece import UnstringPiece


@dataclass(frozen=True)
class UnstringOutcome:
    pieces: tuple[UnstringPiece, ...]
    pointer: int
    overflow: bool
