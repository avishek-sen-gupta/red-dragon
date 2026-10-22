# pyright: standard
"""A comparison outcome with the conditions it raised."""

from dataclasses import dataclass

from zarch_float.comparison import Comparison
from zarch_float.condition import Condition


@dataclass(frozen=True)
class ComparisonResult:
    comparison: Comparison
    conditions: frozenset[Condition]
