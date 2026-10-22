# pyright: standard
"""BFP format, integral and fixed-point conversions (PoO chapter 19)."""

from collections.abc import Callable, Mapping
from fractions import Fraction

from zarch_float.bfp_format import EXTENDED, LONG, BfpFormat
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_rounding import BfpRounding, rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition, raised
from zarch_float.exact_rounding import round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import IntegerFormat
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode

_LOAD_ROUNDED_TRAP_SCALE: Mapping[BfpFormat, int] = {LONG: 512, EXTENDED: 8192}
_OUT_OF_RANGE = frozenset({Condition.INVALID, Condition.INEXACT})


def _resized_nan(value: BfpValue, target: BfpFormat) -> BfpResult:
    widening = target.precision - value.format.precision
    payload = (
        value.significand << widening
        if widening >= 0
        else value.significand >> -widening
    )
    quiet = BfpValue(target, value.negative, FloatKind.QNAN, payload)
    return bfp_exact(quiet, raised((Condition.INVALID, value.kind is FloatKind.SNAN)))


def _resized_special(value: BfpValue, target: BfpFormat) -> BfpResult:
    return bfp_exact(BfpValue(target, value.negative, value.kind))


def _resized(value: BfpValue, rounding: BfpRounding) -> BfpResult:
    resizes: Mapping[FloatKind, Callable[[], BfpResult]] = {
        FloatKind.QNAN: lambda: _resized_nan(value, rounding.target),
        FloatKind.SNAN: lambda: _resized_nan(value, rounding.target),
        FloatKind.ZERO: lambda: _resized_special(value, rounding.target),
        FloatKind.INFINITY: lambda: _resized_special(value, rounding.target),
        FloatKind.FINITE: lambda: rounding.round(value.negative, value.magnitude()),
    }
    return resizes[value.kind]()


def bfp_load_lengthened(a: BfpValue, target: BfpFormat) -> BfpResult:
    return _resized(a, rounding_into(target, RoundingMode.NEAREST_EVEN))


def bfp_load_rounded(a: BfpValue, target: BfpFormat, mode: RoundingMode) -> BfpResult:
    scale = _LOAD_ROUNDED_TRAP_SCALE[a.format]
    return _resized(a, BfpRounding(target, mode, a.format, scale))


def _integral(a: BfpValue, mode: RoundingMode) -> BfpResult:
    magnitude = a.magnitude()
    rounded = round_ratio(magnitude.numerator, magnitude.denominator, mode, a.negative)
    conditions = raised(
        (Condition.INEXACT, rounded.inexact),
        (Condition.INCREMENTED, rounded.incremented),
    )
    return bfp_exact(_integer_value(a, rounded.magnitude), conditions)


def _integer_value(a: BfpValue, magnitude: int) -> BfpValue:
    if magnitude == 0:
        return BfpValue(a.format, a.negative, FloatKind.ZERO)
    exact = rounding_into(a.format, RoundingMode.NEAREST_EVEN)
    return exact.round(a.negative, Fraction(magnitude)).value


def bfp_round_to_integral(a: BfpValue, mode: RoundingMode) -> BfpResult:
    if a.kind is FloatKind.FINITE:
        return _integral(a, mode)
    return _resized(a, rounding_into(a.format, mode))


def bfp_from_integer(n: int, target: BfpFormat, mode: RoundingMode) -> BfpResult:
    if n == 0:
        return bfp_exact(BfpValue(target, False, FloatKind.ZERO))
    return rounding_into(target, mode).round(n < 0, Fraction(abs(n)))


def _finite_to_integer(
    a: BfpValue, target: IntegerFormat, mode: RoundingMode
) -> IntegerResult:
    magnitude = a.magnitude()
    rounded = round_ratio(magnitude.numerator, magnitude.denominator, mode, a.negative)
    n = -rounded.magnitude if a.negative else rounded.magnitude
    if not target.holds(n):
        return IntegerResult(target.clamp(n), _OUT_OF_RANGE)
    conditions = raised(
        (Condition.INEXACT, rounded.inexact),
        (Condition.INCREMENTED, rounded.incremented),
    )
    return IntegerResult(n, conditions)


def _infinite_to_integer(a: BfpValue, target: IntegerFormat) -> IntegerResult:
    return IntegerResult(
        target.minimum if a.negative else target.maximum, _OUT_OF_RANGE
    )


def bfp_to_integer(
    a: BfpValue, target: IntegerFormat, mode: RoundingMode
) -> IntegerResult:
    conversions: Mapping[FloatKind, Callable[[], IntegerResult]] = {
        FloatKind.QNAN: lambda: IntegerResult(target.minimum, _OUT_OF_RANGE),
        FloatKind.SNAN: lambda: IntegerResult(target.minimum, _OUT_OF_RANGE),
        FloatKind.INFINITY: lambda: _infinite_to_integer(a, target),
        FloatKind.ZERO: lambda: IntegerResult(0, frozenset()),
        FloatKind.FINITE: lambda: _finite_to_integer(a, target, mode),
    }
    return conversions[a.kind]()
