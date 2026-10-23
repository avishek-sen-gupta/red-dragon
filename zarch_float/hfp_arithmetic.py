# pyright: standard
"""HFP add, subtract, compare, multiply, multiply and add, divide, halve, square root and load FP integer (PoO chapter 18)."""

from fractions import Fraction
from math import isqrt

from zarch_float.comparison_result import ComparisonResult
from zarch_float.condition import Condition
from zarch_float.hfp_format import EXTENDED, HfpFormat
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_truncation import in_range, normalized, true_zero, truncated
from zarch_float.hfp_value import HfpValue
from zarch_float.ordering import ordered


def _guarded(value: HfpValue, exponent: int) -> int:
    aligned = (value.fraction << 4) >> (4 * (exponent - value.exponent))
    return -aligned if value.negative else aligned


def _intermediate_sum(a: HfpValue, b: HfpValue) -> tuple[int, int]:
    exponent = max(a.exponent, b.exponent)
    return _guarded(a, exponent) + _guarded(b, exponent), exponent


def _unnormalized(target: HfpFormat, total: int, exponent: int) -> HfpValue:
    carry = int(abs(total) >> (4 * (target.digits + 1)) != 0)
    fraction = abs(total) >> (4 * (1 + carry))
    return HfpValue(target, total < 0 and fraction != 0, fraction, exponent + carry)


def _sum(a: HfpValue, b: HfpValue, normalize: bool) -> HfpResult:
    total, exponent = _intermediate_sum(a, b)
    rough = _unnormalized(a.format, total, exponent)
    if rough.fraction == 0 and (total == 0 or not normalize):
        return HfpResult(rough, frozenset({Condition.HFP_SIGNIFICANCE}))
    if normalize:
        unit = Fraction(16) ** (exponent - a.format.digits - 1)
        return in_range(normalized(a.format, total < 0, abs(total) * unit))
    return in_range(rough)


def hfp_add(a: HfpValue, b: HfpValue, normalize: bool) -> HfpResult:
    return _sum(a, b, normalize)


def hfp_subtract(a: HfpValue, b: HfpValue, normalize: bool) -> HfpResult:
    return _sum(a, b.negated(), normalize)


def hfp_compare(a: HfpValue, b: HfpValue) -> ComparisonResult:
    total, _ = _intermediate_sum(a, b.negated())
    return ComparisonResult(
        ordered((0, Fraction(total)), (0, Fraction(0))), frozenset()
    )


def hfp_multiply(a: HfpValue, b: HfpValue, target: HfpFormat) -> HfpResult:
    product = a.magnitude() * b.magnitude()
    return truncated(target, a.negative != b.negative, product)


def hfp_divide(a: HfpValue, b: HfpValue) -> HfpResult:
    if b.fraction == 0:
        return HfpResult(a, frozenset({Condition.HFP_DIVIDE}))
    return truncated(a.format, a.negative != b.negative, a.magnitude() / b.magnitude())


def hfp_halve(a: HfpValue) -> HfpResult:
    return truncated(a.format, a.negative, a.magnitude() / 2)


def _root(a: HfpValue) -> HfpResult:
    operand = normalized(a.format, False, a.magnitude())
    exponent = -(-operand.exponent // 2)
    digits = a.format.digits
    shift = 4 * (operand.exponent + digits + 2 - 2 * exponent)
    guarded = isqrt(operand.fraction << shift)
    return HfpResult(
        HfpValue(a.format, False, (guarded + 8) >> 4, exponent), frozenset()
    )


def hfp_square_root(a: HfpValue) -> HfpResult:
    if a.fraction == 0:
        return HfpResult(true_zero(a.format), frozenset())
    if a.negative:
        return HfpResult(a, frozenset({Condition.HFP_SQUARE_ROOT}))
    return _root(a)


def hfp_load_fp_integer(a: HfpValue) -> HfpResult:
    magnitude = a.magnitude()
    whole = magnitude.numerator // magnitude.denominator
    return truncated(a.format, a.negative, Fraction(whole))


def _fused(a: HfpValue, b: HfpValue, c: HfpValue) -> HfpResult:
    total = a.signed() * b.signed() + c.signed()
    return truncated(c.format, total < 0, abs(total))


def hfp_multiply_add(a: HfpValue, b: HfpValue, c: HfpValue) -> HfpResult:
    return _fused(a, b, c)


def hfp_multiply_subtract(a: HfpValue, b: HfpValue, c: HfpValue) -> HfpResult:
    return _fused(a, b, c.negated())


def hfp_multiply_unnormalized(a: HfpValue, b: HfpValue) -> HfpResult:
    product = HfpValue(
        EXTENDED,
        a.negative != b.negative,
        a.fraction * b.fraction,
        a.exponent + b.exponent,
    )
    return HfpResult(product, frozenset())


def hfp_multiply_add_unnormalized(a: HfpValue, b: HfpValue, c: HfpValue) -> HfpResult:
    product = hfp_multiply_unnormalized(a, b).value
    unit = Fraction(16) ** (product.exponent - EXTENDED.digits)
    total = (product.signed() + c.signed()) / unit
    window = int(abs(total)) % 16**EXTENDED.digits
    return HfpResult(
        HfpValue(EXTENDED, total < 0, window, product.exponent), frozenset()
    )
