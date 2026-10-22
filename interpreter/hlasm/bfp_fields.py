# pyright: standard
"""The sign, biased exponent and fraction IR splits a BFP image into, and the zarch_float value they denote."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_value import BfpValue
from zarch_float.float_kind import FloatKind


@dataclass(frozen=True)
class BfpFields:
    negative: bool
    biased_exponent: int
    fraction: int

    def as_list(self) -> list[int]:
        return [int(self.negative), self.biased_exponent, self.fraction]


def _fraction_bits(fmt: BfpFormat) -> int:
    return fmt.precision - 1


def _top(fmt: BfpFormat) -> int:
    return 2 * fmt.emax + 1


def _quiet(fmt: BfpFormat) -> int:
    return 1 << (fmt.precision - 2)


def _special(fields: BfpFields, fmt: BfpFormat) -> BfpValue:
    kinds = {
        (False, False): FloatKind.INFINITY,
        (True, False): FloatKind.SNAN,
        (True, True): FloatKind.QNAN,
    }
    quiet = bool(fields.fraction & _quiet(fmt))
    kind = kinds[(fields.fraction != 0, quiet)]
    payload = fields.fraction & (_quiet(fmt) - 1)
    return BfpValue(fmt, fields.negative, kind, payload)


def _numeric(fields: BfpFields, fmt: BfpFormat) -> BfpValue:
    if fields.biased_exponent == 0 and fields.fraction == 0:
        return BfpValue(fmt, fields.negative, FloatKind.ZERO)
    implied = int(fields.biased_exponent != 0) << _fraction_bits(fmt)
    exponent = max(fields.biased_exponent, 1) - fmt.emax - _fraction_bits(fmt)
    return BfpValue(
        fmt, fields.negative, FloatKind.FINITE, implied | fields.fraction, exponent
    )


def value_of(fields: BfpFields, fmt: BfpFormat) -> BfpValue:
    if fields.biased_exponent == _top(fmt):
        return _special(fields, fmt)
    return _numeric(fields, fmt)


def _finite(value: BfpValue) -> BfpFields:
    fmt = value.format
    normal = value.significand >> _fraction_bits(fmt)
    biased = (value.exponent + _fraction_bits(fmt) + fmt.emax) * normal
    fraction = value.significand & ((1 << _fraction_bits(fmt)) - 1)
    return BfpFields(value.negative, biased, fraction)


_FIELDS: Mapping[FloatKind, Callable[[BfpValue], BfpFields]] = {
    FloatKind.ZERO: lambda v: BfpFields(v.negative, 0, 0),
    FloatKind.FINITE: _finite,
    FloatKind.INFINITY: lambda v: BfpFields(v.negative, _top(v.format), 0),
    FloatKind.QNAN: lambda v: BfpFields(
        v.negative, _top(v.format), _quiet(v.format) | v.significand
    ),
    FloatKind.SNAN: lambda v: BfpFields(v.negative, _top(v.format), v.significand),
}


def fields_of(value: BfpValue) -> BfpFields:
    return _FIELDS[value.kind](value)
