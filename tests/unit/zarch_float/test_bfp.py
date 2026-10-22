# pyright: standard
"""BFP arithmetic, rounding and exception conditions against the PoO and host floats."""

import ctypes
import math
import operator
import sys
from collections.abc import Callable

from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.bfp_bits import (
    from_bits,
    long_bits,
    long_of,
    short_bits,
    short_of,
    to_bits,
)
from zarch_float.bfp_arithmetic import (
    bfp_add,
    bfp_divide,
    bfp_multiply,
    bfp_multiply_add,
    bfp_multiply_subtract,
    bfp_square_root,
    bfp_subtract,
)
from zarch_float.bfp_compare import bfp_compare, bfp_compare_signaling
from zarch_float.bfp_convert import (
    bfp_from_integer,
    bfp_load_lengthened,
    bfp_load_rounded,
    bfp_round_to_integral,
    bfp_to_integer,
    bfp_widened,
)
from zarch_float.bfp_format import EXTENDED, LONG, SHORT
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_value import BfpValue
from zarch_float.comparison import Comparison
from zarch_float.comparison_result import ComparisonResult
from zarch_float.condition import Condition
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import SIGNED_32, SIGNED_64, UNSIGNED_32
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode

NE = RoundingMode.NEAREST_EVEN
DMIN = 5e-324
NMIN = sys.float_info.min
NMAX = sys.float_info.max
HALF_ULP = 2.0**-53

INVALID = frozenset({Condition.INVALID})
INEXACT = frozenset({Condition.INEXACT})
UP = frozenset({Condition.INEXACT, Condition.INCREMENTED})
OVER_UP = frozenset({Condition.OVERFLOW, Condition.INEXACT, Condition.INCREMENTED})
OVER = frozenset({Condition.OVERFLOW, Condition.INEXACT})
NONE: frozenset[Condition] = frozenset()

type Binary = Callable[[float, float], float]


def _hard_cases(
    half_ulp: float, dmin: float, nmin: float, nmax: float
) -> list[tuple[Binary, float, float]]:
    return [
        (operator.add, 1.0, half_ulp),
        (operator.add, 1.0 + 2 * half_ulp, half_ulp),
        (operator.add, 1.0, half_ulp * 1.5),
        (operator.sub, 1.0 + 2 * half_ulp, 1.0),
        (operator.add, -0.0, 0.0),
        (operator.add, -0.0, -0.0),
        (operator.sub, 3.5, 3.5),
        (operator.add, dmin, dmin),
        (operator.add, nmin - dmin, dmin),
        (operator.add, nmax, nmax),
        (operator.mul, -nmax, 2.0),
        (operator.mul, nmin * 0.01, 1e-5),
        (operator.mul, dmin, 0.5),
        (operator.mul, 3 * dmin, 0.5),
        (operator.mul, -0.0, 5.0),
        (operator.truediv, 1.0, 3.0),
        (operator.truediv, -2.0, 3.0),
        (operator.truediv, nmin, nmax),
        (operator.truediv, nmax, 0.5),
        (operator.truediv, 0.0, -3.0),
        (operator.truediv, 7.0, -math.inf),
        (operator.add, -math.inf, 1.0),
    ]


LONG_CASES = _hard_cases(HALF_ULP, DMIN, NMIN, NMAX)
SHORT_CASES = _hard_cases(2.0**-24, 2.0**-149, 2.0**-126, (2 - 2.0**-23) * 2.0**127)
ROOT_CASES = [2.0, 4.0, 1e-320, NMAX, -0.0, 0.1, math.inf]


def _long_bits(operation: Binary, a: float, b: float) -> int:
    return long_bits(operation(a, b))


def _short_bits(operation: Binary, a: float, b: float) -> int:
    narrow_a, narrow_b = ctypes.c_float(a).value, ctypes.c_float(b).value
    return short_bits(operation(narrow_a, narrow_b))


_LEAF = {
    operator.add: bfp_add,
    operator.sub: bfp_subtract,
    operator.mul: bfp_multiply,
    operator.truediv: bfp_divide,
}


def _leaf_bits(
    of: Callable[[float], BfpValue], operation: Binary, a: float, b: float
) -> int:
    return to_bits(_LEAF[operation](of(a), of(b), NE).value)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_to_nearest_matches_host_binary64_and_binary32():
    host_long = [_long_bits(op, a, b) for op, a, b in LONG_CASES]
    host_short = [_short_bits(op, a, b) for op, a, b in SHORT_CASES]
    host_roots = [long_bits(math.sqrt(x)) if x >= 0 else 0 for x in ROOT_CASES]
    host_fma = [
        long_bits(math.fma(0.1, 10.0, -1.0)),
        long_bits(math.fma(NMIN, 0.5, DMIN)),
    ]

    assert [_leaf_bits(long_of, op, a, b) for op, a, b in LONG_CASES] == host_long
    assert [_leaf_bits(short_of, op, a, b) for op, a, b in SHORT_CASES] == host_short
    assert [
        to_bits(bfp_square_root(long_of(x), NE).value) for x in ROOT_CASES
    ] == host_roots
    assert [
        to_bits(bfp_multiply_add(long_of(0.1), long_of(10.0), long_of(-1.0), NE).value),
        to_bits(bfp_multiply_add(long_of(NMIN), long_of(0.5), long_of(DMIN), NE).value),
    ] == host_fma


FIGURE_9_11_INPUTS = [-9.5, -5.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 5.5, 9.5]
FIGURE_9_11_BINARY = {
    RoundingMode.NEAREST_EVEN: [-10, -6, -2, -2, -0.0, 0, 2, 2, 6, 10],
    RoundingMode.TOWARD_ZERO: [-9, -5, -2, -1, -0.0, 0, 1, 2, 5, 9],
    RoundingMode.TOWARD_POSITIVE: [-9, -5, -2, -1, -0.0, 1, 2, 3, 6, 10],
    RoundingMode.TOWARD_NEGATIVE: [-10, -6, -3, -2, -1, 0, 1, 2, 5, 9],
    RoundingMode.NEAREST_AWAY: [-10, -6, -3, -2, -1, 1, 2, 3, 6, 10],
    RoundingMode.NEAREST_TOWARD_ZERO: [-9, -5, -2, -1, -0.0, 0, 1, 2, 5, 9],
    RoundingMode.AWAY_FROM_ZERO: [-10, -6, -3, -2, -1, 1, 2, 3, 6, 10],
    RoundingMode.PREPARE_SHORTER: [-9, -5, -3, -1, -1, 1, 1, 3, 5, 9],
}


def _integral_bits(mode: RoundingMode) -> list[int]:
    return [
        to_bits(bfp_round_to_integral(long_of(x), mode).value)
        for x in FIGURE_9_11_INPUTS
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_to_integral_follows_figure_9_11_binary_column():
    expected = {
        mode: [long_bits(float(x)) for x in row]
        for mode, row in FIGURE_9_11_BINARY.items()
    }

    assert {mode: _integral_bits(mode) for mode in FIGURE_9_11_BINARY} == expected
    assert bfp_round_to_integral(long_of(2.5), NE).conditions == INEXACT
    assert (
        bfp_round_to_integral(long_of(2.5), RoundingMode.TOWARD_POSITIVE).conditions
        == UP
    )
    assert bfp_round_to_integral(long_of(-7.0), NE).conditions == NONE


def _long(result: BfpResult) -> tuple[int, frozenset[Condition]]:
    return to_bits(result.value), result.conditions


def _scaled(result: BfpResult) -> tuple[BfpValue, frozenset[Condition]]:
    return result.scaled, result.scaled_conditions


TOWARD = {
    RoundingMode.NEAREST_EVEN: (math.inf, OVER_UP),
    RoundingMode.TOWARD_ZERO: (NMAX, OVER),
    RoundingMode.PREPARE_SHORTER: (NMAX, OVER),
    RoundingMode.TOWARD_NEGATIVE: (NMAX, OVER),
    RoundingMode.TOWARD_POSITIVE: (math.inf, OVER_UP),
    RoundingMode.AWAY_FROM_ZERO: (math.inf, OVER_UP),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_overflow_and_underflow_follow_figure_19_9():
    doubled = {
        mode: _long(bfp_multiply(long_of(NMAX), long_of(2.0), mode)) for mode in TOWARD
    }
    just_below_nmin = bfp_multiply(long_of(1.0 - HALF_ULP), long_of(NMIN), NE)
    exact_subnormal = bfp_multiply(long_of(4 * DMIN), long_of(0.25), NE)
    below_nmin_by_a_quarter_ulp = BfpValue(
        EXTENDED, False, FloatKind.FINITE, (2**54 - 1) << 59, -1076 - 59
    )

    assert doubled == {mode: (long_bits(v), c) for mode, (v, c) in TOWARD.items()}
    assert _scaled(bfp_multiply(long_of(NMAX), long_of(2.0), NE)) == (
        BfpValue(LONG, False, FloatKind.FINITE, 2**53 - 1, 972 - 1536),
        NONE,
    )
    assert _long(just_below_nmin) == (
        long_bits(NMIN),
        frozenset(
            {
                Condition.TINY,
                Condition.UNDERFLOW,
                Condition.INEXACT,
                Condition.INCREMENTED,
            }
        ),
    )
    assert _scaled(just_below_nmin) == (
        BfpValue(LONG, False, FloatKind.FINITE, 2**53 - 1, -1075 + 1536),
        NONE,
    )
    assert _long(exact_subnormal) == (long_bits(DMIN), frozenset({Condition.TINY}))
    assert _long(bfp_load_rounded(below_nmin_by_a_quarter_ulp, LONG, NE)) == (
        long_bits(NMIN),
        frozenset(
            {
                Condition.TINY,
                Condition.UNDERFLOW,
                Condition.INEXACT,
                Condition.INCREMENTED,
            }
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_and_division_by_zero_deliver_default_results():
    default_nan = long_bits(math.nan)

    assert _long(bfp_divide(long_of(0.0), long_of(-0.0), NE)) == (default_nan, INVALID)
    assert _long(bfp_divide(long_of(-1.0), long_of(0.0), NE)) == (
        long_bits(-math.inf),
        frozenset({Condition.DIVISION_BY_ZERO}),
    )
    assert _long(bfp_subtract(long_of(math.inf), long_of(math.inf), NE)) == (
        default_nan,
        INVALID,
    )
    assert _long(bfp_multiply(long_of(-0.0), long_of(math.inf), NE)) == (
        default_nan,
        INVALID,
    )
    assert _long(bfp_square_root(long_of(-4.0), NE)) == (default_nan, INVALID)
    assert _long(
        bfp_subtract(long_of(2.0), long_of(2.0), RoundingMode.TOWARD_NEGATIVE)
    ) == (
        long_bits(-0.0),
        NONE,
    )


def _nan(negative: bool, kind: FloatKind, payload: int) -> BfpValue:
    return BfpValue(LONG, negative, kind, payload)


QUIET_A = _nan(False, FloatKind.QNAN, 0xA)
QUIET_B = _nan(True, FloatKind.QNAN, 0xB)
SIGNAL_C = _nan(True, FloatKind.SNAN, 0xC)
SIGNAL_D = _nan(False, FloatKind.SNAN, 0xD)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_nans_propagate_in_operand_order_and_compare_unordered():
    one, zero, infinity = long_of(1.0), long_of(0.0), long_of(math.inf)
    quiet_c, quiet_d = _nan(True, FloatKind.QNAN, 0xC), _nan(False, FloatKind.QNAN, 0xD)

    assert bfp_add(QUIET_A, QUIET_B, NE).value == QUIET_A
    assert bfp_add(QUIET_A, SIGNAL_C, NE).value == quiet_c
    assert bfp_divide(SIGNAL_D, SIGNAL_C, NE).value == quiet_d
    assert bfp_multiply_add(QUIET_A, one, SIGNAL_C, NE).conditions == INVALID
    assert bfp_multiply_add(QUIET_A, one, SIGNAL_C, NE).value == quiet_c
    assert bfp_multiply_add(zero, infinity, QUIET_B, NE).value == BfpValue(
        LONG, False, FloatKind.QNAN
    )
    assert bfp_multiply_subtract(one, one, QUIET_B, NE).value == QUIET_B
    assert [
        bfp_compare(QUIET_A, one),
        bfp_compare(one, SIGNAL_C),
        bfp_compare_signaling(one, QUIET_A),
        bfp_compare(long_of(-0.0), zero),
        bfp_compare(long_of(-math.inf), long_of(-NMAX)),
        bfp_compare(long_of(1.0 + 2 * HALF_ULP), one),
    ] == [
        ComparisonResult(Comparison.UNORDERED, NONE),
        ComparisonResult(Comparison.UNORDERED, INVALID),
        ComparisonResult(Comparison.UNORDERED, INVALID),
        ComparisonResult(Comparison.EQUAL, NONE),
        ComparisonResult(Comparison.LOW, NONE),
        ComparisonResult(Comparison.HIGH, NONE),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_format_conversions_round_once_and_resize_nan_payloads():
    narrowed_overflow = bfp_load_rounded(long_of(1e39), SHORT, NE)
    long_quiet = BfpValue(LONG, True, FloatKind.QNAN, (0x5 << 29) | 1)
    short_signal = BfpValue(SHORT, False, FloatKind.SNAN, 0x3)

    assert _short(bfp_load_rounded(long_of(1.0 + 2.0**-24), SHORT, NE)) == (
        short_bits(1.0),
        INEXACT,
    )
    assert _short(narrowed_overflow) == (short_bits(math.inf), OVER_UP)
    assert narrowed_overflow.scaled == BfpValue(
        LONG, False, FloatKind.FINITE, 0xBC1440 << 29, 106 - 29 - 512
    )
    assert bfp_load_rounded(long_quiet, SHORT, NE).value == BfpValue(
        SHORT, True, FloatKind.QNAN, 0x5
    )
    assert bfp_load_lengthened(short_signal, LONG) == bfp_exact(
        BfpValue(LONG, False, FloatKind.QNAN, 0x3 << 29), INVALID
    )
    assert bfp_load_lengthened(short_of(2.0**-149), LONG).value == long_of(2.0**-149)
    assert _value(bfp_divide(_extended(1), _extended(3), NE)) == (
        BfpValue(EXTENDED, False, FloatKind.FINITE, (2**114 - 1) // 3, -114),
        INEXACT,
    )


def _value(result: BfpResult) -> tuple[BfpValue, frozenset[Condition]]:
    return result.value, result.conditions


def _short(result: BfpResult) -> tuple[int, frozenset[Condition]]:
    return to_bits(result.value), result.conditions


def _extended(n: int) -> BfpValue:
    return bfp_from_integer(n, EXTENDED, NE).value


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fixed_point_conversions_round_and_saturate():
    out_of_range = frozenset({Condition.INVALID, Condition.INEXACT})
    toward_zero = RoundingMode.TOWARD_ZERO

    assert _long(bfp_from_integer(2**53 + 1, LONG, NE)) == (long_bits(2.0**53), INEXACT)
    assert _long(bfp_from_integer(2**53 + 1, LONG, RoundingMode.TOWARD_POSITIVE)) == (
        long_bits(2.0**53 + 2),
        UP,
    )
    assert _short(bfp_from_integer(-16777217, SHORT, NE)) == (
        short_bits(-16777216.0),
        INEXACT,
    )
    assert _long(bfp_from_integer(0, LONG, NE)) == (long_bits(0.0), NONE)
    assert [
        bfp_to_integer(long_of(2.5), SIGNED_32, NE),
        bfp_to_integer(long_of(-2.5), SIGNED_32, RoundingMode.NEAREST_AWAY),
        bfp_to_integer(long_of(-0.5), UNSIGNED_32, toward_zero),
        bfp_to_integer(long_of(-2.5), UNSIGNED_32, toward_zero),
        bfp_to_integer(long_of(2.0**31), SIGNED_32, NE),
        bfp_to_integer(long_of(-(2.0**31) - 0.5), SIGNED_32, toward_zero),
        bfp_to_integer(QUIET_A, SIGNED_32, NE),
        bfp_to_integer(QUIET_A, UNSIGNED_32, NE),
        bfp_to_integer(long_of(-math.inf), SIGNED_64, NE),
        bfp_to_integer(long_of(-0.0), SIGNED_64, NE),
    ] == [
        IntegerResult(2, INEXACT),
        IntegerResult(-3, UP),
        IntegerResult(0, INEXACT),
        IntegerResult(0, out_of_range),
        IntegerResult(2**31 - 1, out_of_range),
        IntegerResult(-(2**31), INEXACT),
        IntegerResult(-(2**31), out_of_range),
        IntegerResult(0, out_of_range),
        IntegerResult(-(2**63), out_of_range),
        IntegerResult(0, NONE),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_widening_is_exact_and_keeps_signaling_nans():
    assert [
        bfp_widened(short_of(1.5), LONG),
        bfp_widened(short_of(-(2.0**-149)), LONG),
        bfp_widened(short_of(-math.inf), LONG),
        bfp_widened(BfpValue(SHORT, False, FloatKind.SNAN, 1), LONG),
        bfp_widened(long_of(-0.0), LONG),
    ] == [
        long_of(1.5),
        long_of(-(2.0**-149)),
        long_of(-math.inf),
        from_bits(0x7FF00000_20000000, LONG),
        long_of(-0.0),
    ]
