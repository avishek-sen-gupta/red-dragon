"""What an UNSTRING statement leaves, as registers: the pointer, whether the
overflow condition arose, how many receivers were acted on, and each
receiver's piece (meaningful only for the receivers acted on)."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.unstring_ir_piece import UnstringIrPiece
from interpreter.register import Register


@dataclass(frozen=True)
class UnstringIrOutcome:
    pointer: Register
    overflow: Register
    acted: Register
    pieces: tuple[UnstringIrPiece, ...]
