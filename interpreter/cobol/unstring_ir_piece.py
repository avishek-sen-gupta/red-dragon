"""What one UNSTRING receiver is given, as registers: its characters, the
delimiter that ended them (empty at the end of the source) and the count examined."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class UnstringIrPiece:
    text: Register
    delimiter: Register
    count: Register
