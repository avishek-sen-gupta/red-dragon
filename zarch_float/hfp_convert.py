# pyright: standard
"""HFP conversions to fixed point and to BFP."""

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.exact_rounding import round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_value import HfpValue
from zarch_float.integer_format import IntegerFormat
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode


def hfp_to_integer(
    a: HfpValue, target: IntegerFormat, mode: RoundingMode
) -> IntegerResult:
    magnitude = a.magnitude()
    rounded = round_ratio(magnitude.numerator, magnitude.denominator, mode, a.negative)
    n = -rounded.magnitude if a.negative else rounded.magnitude
    if target.holds(n):
        return IntegerResult(n, frozenset())
    return IntegerResult(target.clamp(n), frozenset({Condition.OUT_OF_RANGE}))


def hfp_to_bfp(a: HfpValue, target: BfpFormat, mode: RoundingMode) -> BfpResult:
    if a.fraction == 0:
        return bfp_exact(BfpValue(target, a.negative, FloatKind.ZERO))
    return rounding_into(target, mode).round(a.negative, a.magnitude())
