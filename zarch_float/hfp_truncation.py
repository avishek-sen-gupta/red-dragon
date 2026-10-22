# pyright: standard
"""Normalizes and truncates exact HFP values, and reports exponents out of range."""

from fractions import Fraction

from zarch_float.condition import Condition, raised
from zarch_float.exact_rounding import leading_exponent
from zarch_float.hfp_format import HfpFormat
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_value import HfpValue

MIN_EXPONENT = -64
MAX_EXPONENT = 63


def true_zero(target: HfpFormat) -> HfpValue:
    return HfpValue(target, False, 0, MIN_EXPONENT)


def in_range(value: HfpValue) -> HfpResult:
    return HfpResult(
        value,
        raised(
            (Condition.HFP_EXPONENT_OVERFLOW, value.exponent > MAX_EXPONENT),
            (
                Condition.HFP_EXPONENT_UNDERFLOW,
                value.exponent < MIN_EXPONENT and value.fraction != 0,
            ),
        ),
    )


def normalized(target: HfpFormat, negative: bool, magnitude: Fraction) -> HfpValue:
    exponent = leading_exponent(magnitude) // 4 + 1
    scaled = magnitude * Fraction(16) ** (target.digits - exponent)
    return HfpValue(target, negative, scaled.numerator // scaled.denominator, exponent)


def truncated(target: HfpFormat, negative: bool, magnitude: Fraction) -> HfpResult:
    if magnitude == 0:
        return HfpResult(true_zero(target), frozenset())
    return in_range(normalized(target, negative, magnitude))
