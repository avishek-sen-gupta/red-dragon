# pyright: standard
"""A radix conversion's nontrap value and the scaled value a trapped overflow or underflow delivers, each with its conditions, and the scaling exponent PFPO returns in GR1."""

from dataclasses import dataclass

from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.dfp_value import DfpValue
from zarch_float.hfp_value import HfpValue

type FloatValue = BfpValue | HfpValue | DfpValue


@dataclass(frozen=True)
class RadixResult:
    value: FloatValue
    conditions: frozenset[Condition]
    scaled: FloatValue
    scaled_conditions: frozenset[Condition]
    scaling: int


def radix_exact(
    value: FloatValue, conditions: frozenset[Condition] = frozenset()
) -> RadixResult:
    return RadixResult(value, conditions, value, frozenset(), 0)
