# pyright: standard
"""The decimal-module boundary: contexts per format and method, and value conversion."""

from collections.abc import Callable, Mapping
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_05UP,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Subnormal,
    Underflow,
)

from zarch_float.condition import Condition
from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

_ROUNDINGS: Mapping[RoundingMode, str] = {
    RoundingMode.NEAREST_EVEN: ROUND_HALF_EVEN,
    RoundingMode.NEAREST_AWAY: ROUND_HALF_UP,
    RoundingMode.NEAREST_TOWARD_ZERO: ROUND_HALF_DOWN,
    RoundingMode.TOWARD_ZERO: ROUND_DOWN,
    RoundingMode.TOWARD_POSITIVE: ROUND_CEILING,
    RoundingMode.TOWARD_NEGATIVE: ROUND_FLOOR,
    RoundingMode.AWAY_FROM_ZERO: ROUND_UP,
    RoundingMode.PREPARE_SHORTER: ROUND_05UP,
}

_SIGNALS: Mapping[type[DecimalException], Condition] = {
    InvalidOperation: Condition.INVALID,
    DivisionByZero: Condition.DIVISION_BY_ZERO,
    Overflow: Condition.OVERFLOW,
    Underflow: Condition.UNDERFLOW,
    Subnormal: Condition.TINY,
    Inexact: Condition.INEXACT,
}

_SPECIAL_KINDS: Mapping[str, FloatKind] = {
    "F": FloatKind.INFINITY,
    "n": FloatKind.QNAN,
    "N": FloatKind.SNAN,
}
_SPECIAL_TEXT: Mapping[FloatKind, Callable[[int], str]] = {
    FloatKind.INFINITY: lambda _: "Infinity",
    FloatKind.QNAN: lambda payload: f"NaN{payload}",
    FloatKind.SNAN: lambda payload: f"sNaN{payload}",
}

type DecimalOperation = Callable[[Context], Decimal]


def bounded(target: DfpFormat, mode: RoundingMode) -> Context:
    return Context(
        prec=target.precision,
        rounding=_ROUNDINGS[mode],
        Emax=target.emax,
        Emin=target.emin,
        clamp=1,
        traps=[],
    )


def unbounded(digits: int, mode: RoundingMode) -> Context:
    return Context(
        prec=digits, rounding=_ROUNDINGS[mode], Emax=MAX_EMAX, Emin=MIN_EMIN, traps=[]
    )


def raised_in(context: Context) -> frozenset[Condition]:
    return frozenset(
        condition for signal, condition in _SIGNALS.items() if context.flags[signal]
    )


def _digits(n: int) -> tuple[int, ...]:
    return tuple(int(digit) for digit in str(n))


def to_decimal(value: DfpValue) -> Decimal:
    if value.is_finite():
        return Decimal(
            (int(value.negative), _digits(value.significand), value.exponent)
        )
    sign = "-" if value.negative else ""
    return Decimal(sign + _SPECIAL_TEXT[value.kind](value.significand))


def _coefficient(number: Decimal) -> int:
    return int("".join(map(str, number.as_tuple().digits)) or "0")


def _special(number: Decimal, target: DfpFormat, code: str) -> DfpValue:
    kind = _SPECIAL_KINDS[code]
    return DfpValue(target, number.is_signed(), kind, _coefficient(number))


def from_decimal(number: Decimal, target: DfpFormat) -> DfpValue:
    parts = number.as_tuple()
    if isinstance(parts.exponent, str):
        return _special(number, target, parts.exponent)
    significand = _coefficient(number)
    kind = FloatKind.FINITE if significand else FloatKind.ZERO
    return DfpValue(target, number.is_signed(), kind, significand, parts.exponent)


def quotient(numerator: int, denominator: int) -> DecimalOperation:
    return lambda context: context.divide(Decimal(numerator), Decimal(denominator))


def to_integral(value: DfpValue, mode: RoundingMode) -> int:
    return int(to_decimal(value).to_integral_value(rounding=_ROUNDINGS[mode]))
