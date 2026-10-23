# pyright: standard
"""The [negative, e, significand] fields the DPD codec gives, and the zarch_float value they denote: e is the biased exponent, or -1 infinity, -2 QNaN, -3 SNaN."""

from collections.abc import Callable, Mapping, Sequence

from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind

INFINITY = -1
QUIET_NAN = -2
SIGNALING_NAN = -3

_SPECIALS: Mapping[int, FloatKind] = {
    INFINITY: FloatKind.INFINITY,
    QUIET_NAN: FloatKind.QNAN,
    SIGNALING_NAN: FloatKind.SNAN,
}


def _finite(negative: bool, e: int, significand: int, fmt: DfpFormat) -> DfpValue:
    kind = FloatKind.FINITE if significand else FloatKind.ZERO
    return DfpValue(fmt, negative, kind, significand, e - fmt.bias)


def _special(negative: bool, e: int, significand: int, fmt: DfpFormat) -> DfpValue:
    kind = _SPECIALS[e]
    payload = 0 if kind is FloatKind.INFINITY else significand
    return DfpValue(fmt, negative, kind, payload)


def dfp_value_of(fields: Sequence[int], fmt: DfpFormat) -> DfpValue:
    negative, e, significand = fields
    build = _finite if e >= 0 else _special
    return build(bool(negative), e, significand, fmt)


_FIELDS: Mapping[FloatKind, Callable[[DfpValue], list[int]]] = {
    FloatKind.ZERO: lambda v: [int(v.negative), v.exponent + v.format.bias, 0],
    FloatKind.FINITE: lambda v: [
        int(v.negative),
        v.exponent + v.format.bias,
        v.significand,
    ],
    FloatKind.INFINITY: lambda v: [int(v.negative), INFINITY, 0],
    FloatKind.QNAN: lambda v: [int(v.negative), QUIET_NAN, v.significand],
    FloatKind.SNAN: lambda v: [int(v.negative), SIGNALING_NAN, v.significand],
}


def dfp_fields_of(value: DfpValue) -> list[int]:
    return _FIELDS[value.kind](value)
