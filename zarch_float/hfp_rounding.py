# pyright: standard
"""Rounds an exact nonzero value into an HFP fraction of any bit length, normalized or at a given exponent; the caller checks the exponent range."""

from fractions import Fraction

from zarch_float.exact_rounding import leading_exponent, round_ratio
from zarch_float.hfp_format import HfpFormat
from zarch_float.hfp_value import HfpValue
from zarch_float.rounding_mode import RoundingMode

_HEX_BASE = Fraction(16)
_BITS_PER_DIGIT = 4


def hfp_rounded_at(
    fraction_bits: int,
    negative: bool,
    magnitude: Fraction,
    exponent: int,
    mode: RoundingMode,
) -> HfpValue:
    scaled = magnitude / _HEX_BASE**exponent * 2**fraction_bits
    rounded = round_ratio(scaled.numerator, scaled.denominator, mode, negative)
    digits = -(-fraction_bits // _BITS_PER_DIGIT)
    padding = _BITS_PER_DIGIT * digits - fraction_bits
    return HfpValue(HfpFormat(digits), negative, rounded.magnitude << padding, exponent)


def hfp_rounded(
    fraction_bits: int,
    negative: bool,
    magnitude: Fraction,
    scale: int,
    mode: RoundingMode,
) -> HfpValue:
    exponent = leading_exponent(magnitude) // _BITS_PER_DIGIT + 1 + scale
    value = hfp_rounded_at(fraction_bits, negative, magnitude, exponent, mode)
    if value.fraction < 1 << (_BITS_PER_DIGIT * value.format.digits):
        return value
    return hfp_rounded_at(fraction_bits, negative, magnitude, exponent + 1, mode)
