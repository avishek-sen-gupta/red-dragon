"""A decoded arithmetic operand or intermediate result, with the scale it carries."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_numeric.scale import Scale
from interpreter.register import Register


@dataclass(frozen=True)
class ArithmeticValue:
    register: Register
    scale: Scale
    floating: bool
