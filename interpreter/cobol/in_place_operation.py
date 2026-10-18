"""An arithmetic verb without GIVING: each receiver becomes itself combined with the sending value."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.arithmetic_value import ArithmeticValue


@dataclass(frozen=True)
class InPlaceOperation:
    op: str
    sending: ArithmeticValue
