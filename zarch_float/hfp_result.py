# pyright: standard
"""An HFP result with its unwrapped exponent and the conditions it raised."""

from dataclasses import dataclass

from zarch_float.condition import Condition
from zarch_float.hfp_value import HfpValue


@dataclass(frozen=True)
class HfpResult:
    value: HfpValue
    conditions: frozenset[Condition]
