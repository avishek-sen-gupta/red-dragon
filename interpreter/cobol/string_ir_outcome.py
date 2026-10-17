"""What a STRING statement leaves, as registers: the receiver's characters, the
pointer, and whether the overflow condition arose."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class StringIrOutcome:
    image: Register
    pointer: Register
    overflow: Register
