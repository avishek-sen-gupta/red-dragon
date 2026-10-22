# pyright: standard
"""A DFP result: the nontrap value and the scaled value a trap delivers, with conditions."""

from dataclasses import dataclass

from zarch_float.condition import Condition
from zarch_float.dfp_value import DfpValue


@dataclass(frozen=True)
class DfpResult:
    value: DfpValue
    conditions: frozenset[Condition]
    scaled: DfpValue
    scaled_conditions: frozenset[Condition]


def dfp_exact(
    value: DfpValue, conditions: frozenset[Condition] = frozenset()
) -> DfpResult:
    return DfpResult(value, conditions, value, frozenset())
