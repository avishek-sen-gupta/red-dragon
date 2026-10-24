# pyright: standard
"""Packs a BFP value into its image: sign, biased exponent and fraction, in a format of any precision (PoO figures 19-1 to 19-4)."""

from collections.abc import Callable, Mapping

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_value import BfpValue
from zarch_float.float_kind import FloatKind


def _fraction_bits(fmt: BfpFormat) -> int:
    return fmt.precision - 1


def _all_ones_exponent(fmt: BfpFormat) -> int:
    return 2 * fmt.emax + 1


def _quiet_bit(fmt: BfpFormat) -> int:
    return 1 << (_fraction_bits(fmt) - 1)


def _packed(value: BfpValue, biased: int, fraction: int) -> int:
    fmt = value.format
    width = _all_ones_exponent(fmt).bit_length() + _fraction_bits(fmt)
    return int(value.negative) << width | biased << _fraction_bits(fmt) | fraction


def _finite(value: BfpValue) -> int:
    fmt = value.format
    normal = value.significand >> _fraction_bits(fmt)
    biased = (value.exponent + _fraction_bits(fmt) + fmt.emax) * normal
    fraction = value.significand & ((1 << _fraction_bits(fmt)) - 1)
    return _packed(value, biased, fraction)


_IMAGES: Mapping[FloatKind, Callable[[BfpValue], int]] = {
    FloatKind.ZERO: lambda v: _packed(v, 0, 0),
    FloatKind.FINITE: _finite,
    FloatKind.INFINITY: lambda v: _packed(v, _all_ones_exponent(v.format), 0),
    FloatKind.QNAN: lambda v: _packed(
        v, _all_ones_exponent(v.format), v.significand | _quiet_bit(v.format)
    ),
    FloatKind.SNAN: lambda v: _packed(v, _all_ones_exponent(v.format), v.significand),
}


def bfp_image(value: BfpValue) -> int:
    return _IMAGES[value.kind](value)
