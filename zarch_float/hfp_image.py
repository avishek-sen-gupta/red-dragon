# pyright: standard
"""Packs an HFP value into the leftmost bits of the long or extended layout: sign, characteristic and fraction, the low half of an extended number with the characteristic less 14 (PoO chapter 18)."""

from zarch_float.hfp_value import HfpValue

_EXCESS = 64
_CHARACTERISTIC_MASK = 0x7F
_LOW_HALF_CHARACTERISTIC_OFFSET = 14
_HALF_WIDTH = 64
_HALF_FRACTION_BITS = 56
_HALF_FRACTION_MASK = (1 << _HALF_FRACTION_BITS) - 1


def _half(negative: bool, characteristic: int, fraction: int) -> int:
    sign = int(negative) << (_HALF_WIDTH - 1)
    return sign | characteristic << _HALF_FRACTION_BITS | fraction


def _long(value: HfpValue, characteristic: int) -> int:
    fraction = value.fraction << (_HALF_FRACTION_BITS - 4 * value.format.digits)
    return _half(value.negative, characteristic, fraction)


def _extended(value: HfpValue, characteristic: int) -> int:
    fraction = value.fraction << (2 * _HALF_FRACTION_BITS - 4 * value.format.digits)
    low_characteristic = (
        characteristic - _LOW_HALF_CHARACTERISTIC_OFFSET
    ) & _CHARACTERISTIC_MASK
    high = _half(value.negative, characteristic, fraction >> _HALF_FRACTION_BITS)
    low = _half(value.negative, low_characteristic, fraction & _HALF_FRACTION_MASK)
    return high << _HALF_WIDTH | low


def hfp_image(value: HfpValue, bits: int) -> int:
    if value.fraction == 0:
        return int(value.negative) << (bits - 1)
    characteristic = value.exponent + _EXCESS
    if bits <= _HALF_WIDTH:
        return _long(value, characteristic) >> (_HALF_WIDTH - bits)
    return _extended(value, characteristic) >> (2 * _HALF_WIDTH - bits)
