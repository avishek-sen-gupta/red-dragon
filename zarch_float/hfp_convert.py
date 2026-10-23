# pyright: standard
"""HFP load rounded and lengthened, and conversions to and from fixed point and to BFP."""

from fractions import Fraction

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.exact_rounding import round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_format import EXTENDED, HfpFormat
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_truncation import MIN_EXPONENT, in_range, truncated
from zarch_float.hfp_value import HfpValue
from zarch_float.integer_format import IntegerFormat
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode


def hfp_load_rounded(a: HfpValue, target: HfpFormat) -> HfpResult:
    dropped = 4 * (a.format.digits - target.digits)
    rounded = (a.fraction + (1 << (dropped - 1))) >> dropped
    carry = rounded >> (4 * target.digits)
    return in_range(
        HfpValue(target, a.negative, rounded >> (4 * carry), a.exponent + carry)
    )


def hfp_load_lengthened(a: HfpValue, target: HfpFormat) -> HfpResult:
    fraction = a.fraction << (4 * (target.digits - a.format.digits))
    true_zero = fraction == 0 and target == EXTENDED
    exponent = MIN_EXPONENT if true_zero else a.exponent
    return HfpResult(HfpValue(target, a.negative, fraction, exponent), frozenset())


def hfp_from_integer(n: int, target: HfpFormat) -> HfpResult:
    return truncated(target, n < 0, Fraction(abs(n)))


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
