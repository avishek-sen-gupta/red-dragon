# pyright: standard
"""DFP add, subtract, multiply, divide, quantize and reround (PoO chapter 20)."""

from collections.abc import Callable, Mapping
from decimal import Context, Decimal
from fractions import Fraction

from zarch_float.condition import Condition, raised
from zarch_float.dfp_context import bounded, from_decimal, to_decimal, unbounded
from zarch_float.dfp_nan import has_nan, invalid, propagate_nan
from zarch_float.dfp_quantum import constrained, quantum_differs, with_quantum
from zarch_float.dfp_result import DfpResult, dfp_exact
from zarch_float.dfp_rounding import Exact, dfp_rounding_into
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

type _Binary = Callable[[Context, Decimal, Decimal], Decimal]


def _binary(
    operation: _Binary, a: DfpValue, b: DfpValue, mode: RoundingMode, exact: Exact
) -> DfpResult:
    operands = to_decimal(a), to_decimal(b)
    rounding = dfp_rounding_into(a.format, mode)
    return rounding.apply(lambda context: operation(context, *operands), exact)


def dfp_add(a: DfpValue, b: DfpValue, mode: RoundingMode) -> DfpResult:
    result = _binary(Context.add, a, b, mode, lambda: a.signed() + b.signed())
    return with_quantum(result, quantum_differs(result, min(a.exponent, b.exponent)))


def dfp_subtract(a: DfpValue, b: DfpValue, mode: RoundingMode) -> DfpResult:
    result = _binary(Context.subtract, a, b, mode, lambda: a.signed() - b.signed())
    return with_quantum(result, quantum_differs(result, min(a.exponent, b.exponent)))


def dfp_multiply(a: DfpValue, b: DfpValue, mode: RoundingMode) -> DfpResult:
    result = _binary(Context.multiply, a, b, mode, lambda: a.signed() * b.signed())
    return with_quantum(result, quantum_differs(result, a.exponent + b.exponent))


def _at_extreme_quantum(value: DfpValue, preferred: int) -> bool:
    at_max = value.exponent == value.format.quantum_max and value.significand % 10 == 0
    at_min = value.exponent == value.format.quantum_min and value.exponent > preferred
    return value.exponent != preferred and (at_max or at_min)


def _divide_quantum(result: DfpResult, a: DfpValue, b: DfpValue) -> bool:
    by_infinity = a.is_finite() and b.kind is FloatKind.INFINITY
    exact_finite = (
        result.value.is_finite() and Condition.INEXACT not in result.conditions
    )
    extreme = exact_finite and _at_extreme_quantum(
        result.value, a.exponent - b.exponent
    )
    return Condition.INEXACT in result.conditions or by_infinity or extreme


def dfp_divide(a: DfpValue, b: DfpValue, mode: RoundingMode) -> DfpResult:
    result = _binary(Context.divide, a, b, mode, lambda: a.signed() / b.signed())
    return with_quantum(result, _divide_quantum(result, a, b))


def _quantize_finite(
    value: DfpValue, quantum: DfpValue, mode: RoundingMode
) -> DfpResult:
    result = _binary(Context.quantize, value, quantum, mode, value.signed)
    return constrained(result, value)


_QUANTIZE: Mapping[
    tuple[bool, bool], Callable[[DfpValue, DfpValue, RoundingMode], DfpResult]
] = {
    (False, False): _quantize_finite,
    (True, True): lambda value, quantum, mode: dfp_exact(value),
    (True, False): lambda value, quantum, mode: invalid(value.format),
    (False, True): lambda value, quantum, mode: invalid(value.format),
}


def dfp_quantize(value: DfpValue, quantum: DfpValue, mode: RoundingMode) -> DfpResult:
    if has_nan((quantum, value)):
        return propagate_nan((quantum, value))
    infinite = (value.kind is FloatKind.INFINITY, quantum.kind is FloatKind.INFINITY)
    return _QUANTIZE[infinite](value, quantum, mode)


def _keeps_value(value: DfpValue, significance: int) -> bool:
    short_enough = len(str(value.significand)) <= significance
    return value.kind is not FloatKind.FINITE or significance == 0 or short_enough


def _largest(value: DfpValue) -> Fraction:
    fmt = value.format
    return (10**fmt.precision - 1) * Fraction(10) ** fmt.quantum_max


def _rerounded(value: DfpValue, significance: int, mode: RoundingMode) -> DfpResult:
    context = unbounded(significance, mode)
    shortened = from_decimal(context.plus(to_decimal(value)), value.format)
    if shortened.magnitude() > _largest(value):
        return invalid(value.format)
    fitted = from_decimal(
        bounded(value.format, mode).create_decimal(to_decimal(shortened)), value.format
    )
    inexact = shortened.magnitude() != value.magnitude()
    rounding = raised(
        (Condition.INEXACT, inexact),
        (Condition.INCREMENTED, shortened.magnitude() > value.magnitude()),
    )
    return constrained(DfpResult(fitted, rounding, fitted, rounding), value)


def dfp_reround(value: DfpValue, significance: int, mode: RoundingMode) -> DfpResult:
    if value.is_nan():
        return propagate_nan((value,))
    if _keeps_value(value, significance):
        return dfp_exact(value)
    return _rerounded(value, significance, mode)
