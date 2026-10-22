# pyright: standard
"""Test-only HFP short and long images, written the way the PoO prints them."""

from zarch_float.hfp_format import LONG, SHORT, HfpFormat
from zarch_float.hfp_value import HfpValue


def _decode(bits: int, fmt: HfpFormat) -> HfpValue:
    width = 4 * fmt.digits
    characteristic = (bits >> width) & 0x7F
    negative = bool(bits >> (width + 7))
    return HfpValue(fmt, negative, bits & ((1 << width) - 1), characteristic - 64)


def _encode(value: HfpValue) -> int:
    width = 4 * value.format.digits
    characteristic = (value.exponent + 64) & 0x7F
    return int(value.negative) << (width + 7) | characteristic << width | value.fraction


def short(bits: int) -> HfpValue:
    return _decode(bits, SHORT)


def long(bits: int) -> HfpValue:
    return _decode(bits, LONG)


def image(value: HfpValue) -> int:
    return _encode(value)
