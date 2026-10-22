# pyright: standard
"""BFP DIVIDE TO INTEGER (PoO figure 19-22): an integer quotient, final or partial, and its remainder."""

from collections.abc import Callable, Mapping
from fractions import Fraction

from zarch_float.bfp_divide_to_integer_result import BfpDivideToIntegerResult
from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_nan import has_nan, invalid, propagate_nan
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.exact_rounding import leading_exponent, round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

type _Rule = Callable[
    [BfpValue, BfpValue, RoundingMode, RoundingMode], BfpDivideToIntegerResult
]


def _same(result: BfpResult) -> BfpDivideToIntegerResult:
    return BfpDivideToIntegerResult(result, result.value, False, False)


def _invalid(
    a: BfpValue, b: BfpValue, quotient: RoundingMode, remainder: RoundingMode
) -> BfpDivideToIntegerResult:
    return _same(invalid(a.format))


def _unchanged(
    a: BfpValue, b: BfpValue, quotient: RoundingMode, remainder: RoundingMode
) -> BfpDivideToIntegerResult:
    zero = BfpValue(a.format, a.negative != b.negative, FloatKind.ZERO)
    return BfpDivideToIntegerResult(bfp_exact(a), zero, False, False)


def _integer_quotient(
    magnitude: Fraction, precision: int, mode: RoundingMode, negative: bool
) -> tuple[int, bool]:
    if magnitude < 2**precision or magnitude.denominator == 1:
        rounded = round_ratio(
            magnitude.numerator, magnitude.denominator, mode, negative
        )
        return rounded.magnitude, False
    quantum = leading_exponent(magnitude) - precision + 1
    return int(magnitude / 2**quantum) << quantum, True


def _quotient_value(fmt: BfpFormat, negative: bool, n: int) -> tuple[BfpValue, bool]:
    if n == 0:
        return BfpValue(fmt, negative, FloatKind.ZERO), False
    exponent = n.bit_length() - fmt.precision
    overflow = exponent > fmt.quantum_max
    significand = (n << fmt.precision) >> n.bit_length()
    scaled = exponent - fmt.trap_scale * int(overflow)
    return BfpValue(fmt, negative, FloatKind.FINITE, significand, scaled), overflow


def _remainder(
    a: BfpValue, exact: Fraction, partial: bool, mode: RoundingMode
) -> BfpResult:
    if exact == 0:
        return bfp_exact(BfpValue(a.format, a.negative, FloatKind.ZERO))
    rounded = rounding_into(a.format, mode).round(exact < 0, abs(exact))
    return bfp_exact(rounded.value) if partial else rounded


def _divided(
    a: BfpValue, b: BfpValue, quotient: RoundingMode, remainder: RoundingMode
) -> BfpDivideToIntegerResult:
    q = a.signed() / b.signed()
    n, partial = _integer_quotient(abs(q), a.format.precision, quotient, q < 0)
    exact = a.signed() - b.signed() * (-n if q < 0 else n)
    value, overflow = _quotient_value(a.format, q < 0, n)
    return BfpDivideToIntegerResult(
        _remainder(a, exact, partial, remainder), value, partial, overflow
    )


_RULES: Mapping[tuple[FloatKind, FloatKind], _Rule] = {
    (FloatKind.FINITE, FloatKind.FINITE): _divided,
    (FloatKind.FINITE, FloatKind.ZERO): _invalid,
    (FloatKind.FINITE, FloatKind.INFINITY): _unchanged,
    (FloatKind.ZERO, FloatKind.FINITE): _unchanged,
    (FloatKind.ZERO, FloatKind.ZERO): _invalid,
    (FloatKind.ZERO, FloatKind.INFINITY): _unchanged,
    (FloatKind.INFINITY, FloatKind.FINITE): _invalid,
    (FloatKind.INFINITY, FloatKind.ZERO): _invalid,
    (FloatKind.INFINITY, FloatKind.INFINITY): _invalid,
}


def bfp_divide_to_integer(
    a: BfpValue, b: BfpValue, quotient: RoundingMode, remainder: RoundingMode
) -> BfpDivideToIntegerResult:
    if has_nan((a, b)):
        return _same(propagate_nan((a, b)))
    return _RULES[(a.kind, b.kind)](a, b, quotient, remainder)
