# pyright: standard
"""DFP format, integral and fixed-point conversions (PoO chapter 20)."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from fractions import Fraction

from zarch_float.condition import Condition, raised
from zarch_float.dfp_context import to_decimal, to_integral
from zarch_float.dfp_format import EXTENDED, LONG, DfpFormat
from zarch_float.dfp_nan import propagate_nan
from zarch_float.dfp_quantum import constrained, quantum_differs, with_quantum
from zarch_float.dfp_result import DfpResult, dfp_exact
from zarch_float.dfp_rounding import DfpRounding, dfp_rounding_into
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import IntegerFormat
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode

_LOAD_ROUNDED_TRAP_SCALE: Mapping[DfpFormat, int] = {LONG: 192, EXTENDED: 3072}
_INVALID = frozenset({Condition.INVALID})


def _resized_nan(value: DfpValue, target: DfpFormat) -> DfpResult:
    quieted = propagate_nan((value,))
    payload = value.significand % 10 ** (target.precision - 1)
    return replace(
        quieted, value=replace(quieted.value, format=target, significand=payload)
    )


def _rounded_finite(
    value: DfpValue, target: DfpFormat, mode: RoundingMode
) -> DfpResult:
    trap_scale = _LOAD_ROUNDED_TRAP_SCALE[value.format]
    rounding = DfpRounding(target, mode, value.format, trap_scale)
    source = to_decimal(value)
    result = rounding.apply(
        lambda context: context.create_decimal(source), value.signed
    )
    return with_quantum(result, quantum_differs(result, value.exponent))


def _resized(
    value: DfpValue, target: DfpFormat, finite: Callable[[], DfpResult]
) -> DfpResult:
    resizes: Mapping[FloatKind, Callable[[], DfpResult]] = {
        FloatKind.QNAN: lambda: _resized_nan(value, target),
        FloatKind.SNAN: lambda: _resized_nan(value, target),
        FloatKind.INFINITY: lambda: dfp_exact(
            DfpValue(target, value.negative, value.kind)
        ),
        FloatKind.ZERO: finite,
        FloatKind.FINITE: finite,
    }
    return resizes[value.kind]()


def dfp_load_lengthened(a: DfpValue, target: DfpFormat) -> DfpResult:
    return _resized(a, target, lambda: dfp_exact(replace(a, format=target)))


def dfp_load_rounded(a: DfpValue, target: DfpFormat, mode: RoundingMode) -> DfpResult:
    return _resized(a, target, lambda: _rounded_finite(a, target, mode))


def _integral(a: DfpValue, mode: RoundingMode) -> DfpResult:
    source = to_decimal(a)
    rounding = dfp_rounding_into(a.format, mode)
    result = rounding.apply(lambda context: context.to_integral_exact(source), a.signed)
    return constrained(result, a)


def dfp_round_to_integral(a: DfpValue, mode: RoundingMode) -> DfpResult:
    return _resized(a, a.format, lambda: _integral(a, mode))


def dfp_from_integer(n: int, target: DfpFormat, mode: RoundingMode) -> DfpResult:
    rounding = dfp_rounding_into(target, mode)
    result = rounding.apply(
        lambda context: context.create_decimal(n), lambda: Fraction(n)
    )
    return with_quantum(result, quantum_differs(result, 0))


def _finite_to_integer(
    a: DfpValue, target: IntegerFormat, mode: RoundingMode
) -> IntegerResult:
    n = to_integral(a, mode)
    if not target.holds(n):
        return IntegerResult(target.clamp(n), _INVALID)
    conditions = raised(
        (Condition.INEXACT, n != a.signed()),
        (Condition.INCREMENTED, abs(n) > a.magnitude()),
    )
    return IntegerResult(n, conditions)


def dfp_to_integer(
    a: DfpValue, target: IntegerFormat, mode: RoundingMode
) -> IntegerResult:
    conversions: Mapping[FloatKind, Callable[[], IntegerResult]] = {
        FloatKind.QNAN: lambda: IntegerResult(target.minimum, _INVALID),
        FloatKind.SNAN: lambda: IntegerResult(target.minimum, _INVALID),
        FloatKind.INFINITY: lambda: IntegerResult(
            target.minimum if a.negative else target.maximum, _INVALID
        ),
        FloatKind.ZERO: lambda: IntegerResult(0, frozenset()),
        FloatKind.FINITE: lambda: _finite_to_integer(a, target, mode),
    }
    return conversions[a.kind]()
