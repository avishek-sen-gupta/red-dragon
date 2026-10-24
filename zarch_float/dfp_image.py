# pyright: standard
"""Packs a DFP value into its image: sign, combination field, exponent continuation and DPD declets (PoO figures 20-1, 20-3 and 20-32)."""

from collections.abc import Callable, Mapping

from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind

_COMBINATION_BITS = 5
_DECLET_BITS = 10
_DIGITS_PER_DECLET = 3
_LARGE_DIGIT = 8
_LARGE_DIGIT_PREFIX = 0b11000
_INFINITY = 0b11110
_NAN = 0b11111
_SNAN_BIT = 1


def _continuation_bits(fmt: DfpFormat) -> int:
    return (fmt.quantum_max - fmt.quantum_min).bit_length() - 2


def _trailing_digits(fmt: DfpFormat) -> int:
    return fmt.precision - 1


def _declet(hundreds: int, tens: int, units: int) -> int:
    bc, fg, jk = (hundreds >> 1) & 0b11, (tens >> 1) & 0b11, (units >> 1) & 0b11
    rows: Mapping[tuple[bool, bool, bool], tuple[int, int, int]] = {
        (False, False, False): (bc, fg, jk),
        (False, False, True): (bc, fg, 0b100),
        (False, True, False): (bc, jk, 0b101),
        (True, False, False): (jk, fg, 0b110),
        (True, True, False): (jk, 0b00, 0b111),
        (True, False, True): (fg, 0b01, 0b111),
        (False, True, True): (bc, 0b10, 0b111),
        (True, True, True): (0b00, 0b11, 0b111),
    }
    large = (hundreds >= _LARGE_DIGIT, tens >= _LARGE_DIGIT, units >= _LARGE_DIGIT)
    top, middle, code = rows[large]
    return (
        top << 8
        | (hundreds & 1) << 7
        | middle << 5
        | (tens & 1) << 4
        | code << 1
        | units & 1
    )


def _declets(fmt: DfpFormat, trailing: int) -> int:
    groups = _trailing_digits(fmt) // _DIGITS_PER_DECLET
    digits = str(trailing).rjust(_trailing_digits(fmt), "0")
    return sum(
        _declet(*(int(d) for d in digits[3 * i : 3 * i + 3]))
        << (_DECLET_BITS * (groups - 1 - i))
        for i in range(groups)
    )


def _width(fmt: DfpFormat) -> int:
    return (
        1
        + _COMBINATION_BITS
        + _continuation_bits(fmt)
        + _DECLET_BITS * _trailing_digits(fmt) // _DIGITS_PER_DECLET
    )


def _packed(value: DfpValue, combination: int, continuation: int, trailing: int) -> int:
    fmt = value.format
    fields = (
        (combination << _continuation_bits(fmt) | continuation)
        << (_DECLET_BITS * _trailing_digits(fmt) // _DIGITS_PER_DECLET)
    ) | _declets(fmt, trailing)
    return int(value.negative) << (_width(fmt) - 1) | fields


def _leading_combination(biased_top: int, leading: int) -> int:
    if leading >= _LARGE_DIGIT:
        return _LARGE_DIGIT_PREFIX | biased_top << 1 | leading & 1
    return biased_top << 3 | leading


def _finite(value: DfpValue) -> int:
    fmt = value.format
    biased = value.exponent + fmt.bias
    leading, trailing = divmod(value.significand, 10 ** _trailing_digits(fmt))
    top = biased >> _continuation_bits(fmt)
    continuation = biased & ((1 << _continuation_bits(fmt)) - 1)
    return _packed(value, _leading_combination(top, leading), continuation, trailing)


def _nan(value: DfpValue, signaling: int) -> int:
    continuation = signaling << (_continuation_bits(value.format) - 1)
    return _packed(value, _NAN, continuation, value.significand)


_IMAGES: Mapping[FloatKind, Callable[[DfpValue], int]] = {
    FloatKind.ZERO: _finite,
    FloatKind.FINITE: _finite,
    FloatKind.INFINITY: lambda v: _packed(v, _INFINITY, 0, 0),
    FloatKind.QNAN: lambda v: _nan(v, 0),
    FloatKind.SNAN: lambda v: _nan(v, _SNAN_BIT),
}


def dfp_image(value: DfpValue) -> int:
    return _IMAGES[value.kind](value)
