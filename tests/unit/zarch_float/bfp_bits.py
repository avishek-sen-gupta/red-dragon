# pyright: standard
"""Test-only BFP bit images, so results can be checked against host binary32/binary64."""

import ctypes
import struct

from zarch_float.bfp_format import LONG, SHORT, BfpFormat
from zarch_float.bfp_value import BfpValue
from zarch_float.float_kind import FloatKind


def _exponent_bits(fmt: BfpFormat) -> int:
    return (2 * fmt.emax + 1).bit_length()


def _fraction_bits(fmt: BfpFormat) -> int:
    return fmt.precision - 1


def _quiet_bit(fmt: BfpFormat) -> int:
    return 1 << (fmt.precision - 2)


def _special(fmt: BfpFormat, negative: bool, fraction: int) -> BfpValue:
    kinds = {
        (False, False): FloatKind.INFINITY,
        (True, False): FloatKind.SNAN,
        (True, True): FloatKind.QNAN,
    }
    kind = kinds[(fraction != 0, bool(fraction & _quiet_bit(fmt)))]
    return BfpValue(fmt, negative, kind, fraction & (_quiet_bit(fmt) - 1))


def _numeric(fmt: BfpFormat, negative: bool, biased: int, fraction: int) -> BfpValue:
    if biased == 0 and fraction == 0:
        return BfpValue(fmt, negative, FloatKind.ZERO)
    implied = int(biased != 0) << _fraction_bits(fmt)
    exponent = max(biased, 1) - fmt.emax - _fraction_bits(fmt)
    return BfpValue(fmt, negative, FloatKind.FINITE, implied | fraction, exponent)


def from_bits(bits: int, fmt: BfpFormat) -> BfpValue:
    fraction = bits & ((1 << _fraction_bits(fmt)) - 1)
    biased = (bits >> _fraction_bits(fmt)) & (2 * fmt.emax + 1)
    negative = bool(bits >> (_exponent_bits(fmt) + _fraction_bits(fmt)))
    if biased == 2 * fmt.emax + 1:
        return _special(fmt, negative, fraction)
    return _numeric(fmt, negative, biased, fraction)


def long_bits(x: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", x))[0]


def short_bits(x: float) -> int:
    return struct.unpack(">I", struct.pack(">f", ctypes.c_float(x).value))[0]


def long_of(x: float) -> BfpValue:
    return from_bits(long_bits(x), LONG)


def short_of(x: float) -> BfpValue:
    return from_bits(short_bits(x), SHORT)
