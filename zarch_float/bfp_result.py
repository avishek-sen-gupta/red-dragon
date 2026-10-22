# pyright: standard
"""A BFP result: the nontrap value and the scaled value a trap delivers, with conditions."""

from dataclasses import dataclass

from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition


@dataclass(frozen=True)
class BfpResult:
    value: BfpValue
    conditions: frozenset[Condition]
    scaled: BfpValue
    scaled_conditions: frozenset[Condition]


def bfp_exact(
    value: BfpValue, conditions: frozenset[Condition] = frozenset()
) -> BfpResult:
    return BfpResult(value, conditions, value, frozenset())
