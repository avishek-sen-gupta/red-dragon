# pyright: standard
"""BFP add, subtract, multiply, divide, square root and fused multiply-add (PoO chapter 19)."""

from collections.abc import Callable, Mapping
from fractions import Fraction
from math import isqrt

from zarch_float.bfp_nan import has_nan, invalid, propagate_nan
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

type _Rule = Callable[[BfpValue, BfpValue, RoundingMode], BfpResult]

_FINITE = frozenset({FloatKind.ZERO, FloatKind.FINITE})
_ZERO_TIMES_INFINITY = frozenset({FloatKind.ZERO, FloatKind.INFINITY})
_PRODUCT_KINDS: Mapping[frozenset[FloatKind], FloatKind] = {
    frozenset({FloatKind.FINITE}): FloatKind.FINITE,
    frozenset({FloatKind.ZERO}): FloatKind.ZERO,
    frozenset({FloatKind.ZERO, FloatKind.FINITE}): FloatKind.ZERO,
    frozenset({FloatKind.INFINITY}): FloatKind.INFINITY,
    frozenset({FloatKind.FINITE, FloatKind.INFINITY}): FloatKind.INFINITY,
}


def _special(template: BfpValue, negative: bool, kind: FloatKind) -> BfpResult:
    return bfp_exact(BfpValue(template.format, negative, kind))


def _settle(value: BfpValue, mode: RoundingMode) -> BfpResult:
    if value.kind is FloatKind.FINITE:
        return rounding_into(value.format, mode).round(
            value.negative, value.magnitude()
        )
    return _special(value, value.negative, value.kind)


def _round_signed(template: BfpValue, total: Fraction, mode: RoundingMode) -> BfpResult:
    return rounding_into(template.format, mode).round(total < 0, abs(total))


def _finite_sum(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    total = a.signed() + b.signed()
    if total == 0:
        same_sign = a.negative == b.negative
        negative = a.negative if same_sign else mode is RoundingMode.TOWARD_NEGATIVE
        return _special(a, negative, FloatKind.ZERO)
    return _round_signed(a, total, mode)


def _infinite_sum(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    if a.negative == b.negative:
        return bfp_exact(a)
    return invalid(a.format)


def _shape(value: BfpValue) -> bool:
    return value.kind in _FINITE


_SUMS: Mapping[tuple[bool, bool], _Rule] = {
    (True, True): _finite_sum,
    (False, True): lambda a, b, mode: _special(a, a.negative, FloatKind.INFINITY),
    (True, False): lambda a, b, mode: _special(a, b.negative, FloatKind.INFINITY),
    (False, False): _infinite_sum,
}


def _sum(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    if has_nan((a, b)):
        return propagate_nan((a, b))
    return _SUMS[(_shape(a), _shape(b))](a, b, mode)


def _numeric_negated(value: BfpValue) -> BfpValue:
    return value if value.is_nan() else value.negated()


def _exact_product(a: BfpValue, b: BfpValue, template: BfpValue) -> BfpValue:
    return BfpValue(
        template.format,
        a.negative != b.negative,
        _PRODUCT_KINDS[frozenset({a.kind, b.kind})],
        a.significand * b.significand,
        a.exponent + b.exponent,
    )


def bfp_add(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    return _sum(a, b, mode)


def bfp_subtract(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    return _sum(a, _numeric_negated(b), mode)


def bfp_multiply(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    if has_nan((a, b)):
        return propagate_nan((a, b))
    if frozenset({a.kind, b.kind}) == _ZERO_TIMES_INFINITY:
        return invalid(a.format)
    return _settle(_exact_product(a, b, a), mode)


def _fused(a: BfpValue, b: BfpValue, c: BfpValue, mode: RoundingMode) -> BfpResult:
    if frozenset({a.kind, b.kind}) == _ZERO_TIMES_INFINITY:
        return invalid(c.format)
    if has_nan((a, b, c)):
        return propagate_nan((a, b, c))
    return _sum(_exact_product(a, b, c), c, mode)


def bfp_multiply_add(
    a: BfpValue, b: BfpValue, c: BfpValue, mode: RoundingMode
) -> BfpResult:
    return _fused(a, b, c, mode)


def bfp_multiply_subtract(
    a: BfpValue, b: BfpValue, c: BfpValue, mode: RoundingMode
) -> BfpResult:
    return _fused(a, b, _numeric_negated(c), mode)


def _quotient(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    return _round_signed(a, a.signed() / b.signed(), mode)


def _signed_special(kind: FloatKind) -> _Rule:
    return lambda a, b, mode: _special(a, a.negative != b.negative, kind)


def _divide_by_zero(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    infinity = BfpValue(a.format, a.negative != b.negative, FloatKind.INFINITY)
    return bfp_exact(infinity, frozenset({Condition.DIVISION_BY_ZERO}))


_QUOTIENTS: Mapping[tuple[FloatKind, FloatKind], _Rule] = {
    (FloatKind.FINITE, FloatKind.FINITE): _quotient,
    (FloatKind.FINITE, FloatKind.ZERO): _divide_by_zero,
    (FloatKind.FINITE, FloatKind.INFINITY): _signed_special(FloatKind.ZERO),
    (FloatKind.ZERO, FloatKind.FINITE): _signed_special(FloatKind.ZERO),
    (FloatKind.ZERO, FloatKind.INFINITY): _signed_special(FloatKind.ZERO),
    (FloatKind.ZERO, FloatKind.ZERO): lambda a, b, mode: invalid(a.format),
    (FloatKind.INFINITY, FloatKind.FINITE): _signed_special(FloatKind.INFINITY),
    (FloatKind.INFINITY, FloatKind.ZERO): _signed_special(FloatKind.INFINITY),
    (FloatKind.INFINITY, FloatKind.INFINITY): lambda a, b, mode: invalid(a.format),
}


def bfp_divide(a: BfpValue, b: BfpValue, mode: RoundingMode) -> BfpResult:
    if has_nan((a, b)):
        return propagate_nan((a, b))
    return _QUOTIENTS[(a.kind, b.kind)](a, b, mode)


def _root(a: BfpValue, mode: RoundingMode) -> BfpResult:
    odd = a.exponent % 2
    guard = a.format.precision + 3
    radicand = (a.significand << odd) << (2 * guard)
    root = isqrt(radicand)
    inexact = int(root * root != radicand)
    magnitude = Fraction(2 * root + inexact, 2) * Fraction(2) ** (
        (a.exponent - odd) // 2 - guard
    )
    return rounding_into(a.format, mode).round(False, magnitude)


_ROOTS: Mapping[
    tuple[FloatKind, bool], Callable[[BfpValue, RoundingMode], BfpResult]
] = {
    (FloatKind.ZERO, False): lambda a, mode: bfp_exact(a),
    (FloatKind.ZERO, True): lambda a, mode: bfp_exact(a),
    (FloatKind.INFINITY, False): lambda a, mode: bfp_exact(a),
    (FloatKind.INFINITY, True): lambda a, mode: invalid(a.format),
    (FloatKind.FINITE, True): lambda a, mode: invalid(a.format),
    (FloatKind.FINITE, False): _root,
}


def bfp_square_root(a: BfpValue, mode: RoundingMode) -> BfpResult:
    if has_nan((a,)):
        return propagate_nan((a,))
    return _ROOTS[(a.kind, a.negative)](a, mode)
