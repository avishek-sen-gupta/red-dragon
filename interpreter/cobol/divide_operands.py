"""The dividend and divisor of a DIVIDE, from which its REMAINDER is computed."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.arithmetic_value import ArithmeticValue


@dataclass(frozen=True)
class DivideOperands:
    dividend: ArithmeticValue
    divisor: ArithmeticValue
