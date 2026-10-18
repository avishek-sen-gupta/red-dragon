"""One step of an arithmetic verb: an operator applied to two decoded values."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.arithmetic_value import ArithmeticValue


@dataclass(frozen=True)
class ArithmeticOperation:
    op: str
    left: ArithmeticValue
    right: ArithmeticValue
