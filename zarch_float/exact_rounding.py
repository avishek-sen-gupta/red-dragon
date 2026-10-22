# pyright: standard
"""Exact-value primitives: rounding a ratio to an integer (binary RFS), the leading bit."""

from collections.abc import Callable, Mapping
from fractions import Fraction

from zarch_float.rounded_integer import RoundedInteger
from zarch_float.rounding_mode import RoundingMode

_ROUNDS_UP: Mapping[RoundingMode, Callable[[int, int, bool], bool]] = {
    RoundingMode.NEAREST_EVEN: lambda kept, half, _: half > 0
    or (half == 0 and kept % 2 == 1),
    RoundingMode.NEAREST_AWAY: lambda _, half, __: half >= 0,
    RoundingMode.NEAREST_TOWARD_ZERO: lambda _, half, __: half > 0,
    RoundingMode.TOWARD_ZERO: lambda _, __, ___: False,
    RoundingMode.TOWARD_POSITIVE: lambda _, __, negative: not negative,
    RoundingMode.TOWARD_NEGATIVE: lambda _, __, negative: negative,
    RoundingMode.AWAY_FROM_ZERO: lambda _, __, ___: True,
    RoundingMode.PREPARE_SHORTER: lambda kept, _, __: kept % 2 == 0,
}


def round_ratio(
    numerator: int, denominator: int, mode: RoundingMode, negative: bool
) -> RoundedInteger:
    kept, remainder = divmod(numerator, denominator)
    half = (2 * remainder > denominator) - (2 * remainder < denominator)
    up = remainder != 0 and _ROUNDS_UP[mode](kept, half, negative)
    return RoundedInteger(kept + int(up), remainder != 0, up)


def leading_exponent(magnitude: Fraction) -> int:
    estimate = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    return estimate - int(magnitude < Fraction(2) ** estimate)
