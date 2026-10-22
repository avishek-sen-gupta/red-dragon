# pyright: standard
"""Rounds an exact non-negative ratio to an integer; prepare-for-shorter is the binary rule."""

from collections.abc import Callable, Mapping

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
