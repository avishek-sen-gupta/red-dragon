# pyright: standard
"""A fixed-point conversion result with the conditions it raised."""

from dataclasses import dataclass

from zarch_float.condition import Condition


@dataclass(frozen=True)
class IntegerResult:
    value: int
    conditions: frozenset[Condition]
