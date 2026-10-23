# pyright: standard
"""DFP arithmetic: rounding methods, preferred quanta and conditions per the PoO."""

from tests.covers import NotLanguageFeature, covers
from zarch_float.condition import Condition
from zarch_float.dfp_arithmetic import (
    dfp_add,
    dfp_divide,
    dfp_multiply,
    dfp_quantize,
    dfp_reround,
    dfp_subtract,
)
from zarch_float.dfp_convert import (
    dfp_from_integer,
    dfp_load_rounded,
    dfp_round_to_integral,
    dfp_to_integer,
)
from zarch_float.dfp_format import EXTENDED, LONG, SHORT, DfpFormat
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import SIGNED_32
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import RoundingMode

NE = RoundingMode.NEAREST_EVEN
RFS = RoundingMode.PREPARE_SHORTER
NONE: frozenset[Condition] = frozenset()
INVALID = frozenset({Condition.INVALID})
QUANTUM = frozenset({Condition.QUANTUM})
INEXACT_Q = frozenset({Condition.INEXACT, Condition.QUANTUM})
UP_Q = frozenset({Condition.INEXACT, Condition.INCREMENTED, Condition.QUANTUM})


def num(coefficient: int, exponent: int, fmt: DfpFormat = LONG) -> DfpValue:
    kind = FloatKind.FINITE if coefficient else FloatKind.ZERO
    return DfpValue(fmt, coefficient < 0, kind, abs(coefficient), exponent)


def negative_zero(exponent: int) -> DfpValue:
    return DfpValue(LONG, True, FloatKind.ZERO, 0, exponent)


def special(kind: FloatKind, negative: bool = False, payload: int = 0) -> DfpValue:
    return DfpValue(LONG, negative, kind, payload)


def out(result: DfpResult) -> tuple[DfpValue, frozenset[Condition]]:
    return result.value, result.conditions


FIGURE_9_11_INPUTS = [-95, -55, -25, -15, -5, 5, 15, 25, 55, 95]
FIGURE_9_11_DECIMAL = {
    RoundingMode.NEAREST_EVEN: [-10, -6, -2, -2, 0, 0, 2, 2, 6, 10],
    RoundingMode.TOWARD_ZERO: [-9, -5, -2, -1, 0, 0, 1, 2, 5, 9],
    RoundingMode.TOWARD_POSITIVE: [-9, -5, -2, -1, 0, 1, 2, 3, 6, 10],
    RoundingMode.TOWARD_NEGATIVE: [-10, -6, -3, -2, -1, 0, 1, 2, 5, 9],
    RoundingMode.NEAREST_AWAY: [-10, -6, -3, -2, -1, 1, 2, 3, 6, 10],
    RoundingMode.NEAREST_TOWARD_ZERO: [-9, -5, -2, -1, 0, 0, 1, 2, 5, 9],
    RoundingMode.AWAY_FROM_ZERO: [-10, -6, -3, -2, -1, 1, 2, 3, 6, 10],
    RoundingMode.PREPARE_SHORTER: [-9, -6, -2, -1, -1, 1, 1, 2, 6, 9],
}


def _integer(source: int, n: int) -> DfpValue:
    return negative_zero(0) if source < 0 and n == 0 else num(n, 0)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_to_integral_follows_figure_9_11_decimal_column():
    rounded = {
        mode: [
            dfp_round_to_integral(num(x, -1), mode).value for x in FIGURE_9_11_INPUTS
        ]
        for mode in FIGURE_9_11_DECIMAL
    }

    assert rounded == {
        mode: [_integer(x, n) for x, n in zip(FIGURE_9_11_INPUTS, row, strict=True)]
        for mode, row in FIGURE_9_11_DECIMAL.items()
    }
    assert dfp_round_to_integral(num(-25, -1), NE).conditions == INEXACT_Q
    assert out(dfp_round_to_integral(num(70, -1), NE)) == (num(7, 0), QUANTUM)
    assert out(dfp_round_to_integral(num(7, 2), NE)) == (num(7, 2), NONE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rounding_examples_of_figures_9_9_and_9_12_to_9_14():
    assert out(dfp_load_rounded(num(10000003, 0), SHORT, NE)) == (
        num(1000000, 1, SHORT),
        INEXACT_Q,
    )
    assert out(dfp_load_rounded(num(99999995, 0), SHORT, RFS)) == (
        num(9999999, 1, SHORT),
        INEXACT_Q,
    )
    assert out(dfp_load_rounded(num(99999995, 0), SHORT, NE)) == (
        num(1000000, 2, SHORT),
        UP_Q,
    )
    assert [
        out(dfp_reround(num(95, 0), 1, RFS)),
        out(dfp_reround(num(150, 0), 1, RFS)),
        out(dfp_reround(num(150, 0), 1, NE)),
        out(dfp_reround(num(101, 0), 2, RFS)),
        out(dfp_reround(num(150, 0), 2, NE)),
        out(dfp_reround(num(150, 0), 3, NE)),
        out(dfp_reround(num(150, 0), 0, NE)),
    ] == [
        (num(9, 1), INEXACT_Q),
        (num(1, 2), INEXACT_Q),
        (num(2, 2), UP_Q),
        (num(11, 1), UP_Q),
        (num(15, 1), QUANTUM),
        (num(150, 0), NONE),
        (num(150, 0), NONE),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_results_take_the_preferred_quantum_or_raise_the_quantum_condition():
    infinity = special(FloatKind.INFINITY)

    assert [
        out(dfp_add(num(130, -2), num(27, -1), NE)),
        out(dfp_add(num(9999999999999999, 0), num(1, 0), NE)),
        out(dfp_multiply(num(15, -1), num(20, -1), NE)),
        out(dfp_divide(num(1, 0), num(4, 0), NE)),
        out(dfp_divide(num(60, -1), num(2, 0), NE)),
        out(dfp_divide(num(1, 0), num(3, 0), NE)),
        out(dfp_divide(num(7, 0), infinity, NE)),
        out(dfp_quantize(num(217, -2), num(1, -1), NE)),
        out(dfp_quantize(num(217, -2), num(1, -3), NE)),
    ] == [
        (num(400, -2), NONE),
        (num(1000000000000000, 1), QUANTUM),
        (num(300, -2), NONE),
        (num(25, -2), NONE),
        (num(30, -1), NONE),
        (num(3333333333333333, -16), INEXACT_Q),
        (num(0, -398), QUANTUM),
        (num(22, -1), UP_Q),
        (num(2170, -3), QUANTUM),
    ]
    assert out(dfp_divide(num(1, 0, EXTENDED), num(3, 0, EXTENDED), NE)) == (
        num(int("3" * 34), -34, EXTENDED),
        INEXACT_Q,
    )
    assert out(dfp_quantize(num(1234567890123456, 0), num(1, -1), NE)) == (
        special(FloatKind.QNAN),
        INVALID,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_overflow_and_tininess_follow_figures_20_5_and_20_6():
    nmax, ten = num(9999999999999999, 369), num(10, 0)
    overflow = frozenset({Condition.OVERFLOW, Condition.INEXACT, Condition.QUANTUM})
    to_infinity = overflow | {Condition.INCREMENTED}
    tiny_up = UP_Q | {Condition.TINY, Condition.UNDERFLOW}

    assert {
        mode: out(dfp_multiply(nmax, ten, mode))
        for mode in (
            NE,
            RFS,
            RoundingMode.TOWARD_ZERO,
            RoundingMode.NEAREST_TOWARD_ZERO,
        )
    } == {
        NE: (special(FloatKind.INFINITY), to_infinity),
        RFS: (nmax, overflow),
        RoundingMode.TOWARD_ZERO: (nmax, overflow),
        RoundingMode.NEAREST_TOWARD_ZERO: (special(FloatKind.INFINITY), to_infinity),
    }
    assert dfp_multiply(nmax, ten, NE).scaled == num(9999999999999999, 370 - 576)
    assert out(dfp_multiply(num(9999999999999999, -398), num(1, -1), NE)) == (
        num(1000000000000000, -398),
        tiny_up,
    )
    assert out(dfp_multiply(num(1, -398), num(5, -1), NE)) == (
        num(0, -398),
        frozenset(
            {Condition.TINY, Condition.UNDERFLOW, Condition.INEXACT, Condition.QUANTUM}
        ),
    )
    assert dfp_multiply(num(1, -398), num(5, -1), NE).scaled == num(5, -399 + 576)
    assert out(dfp_multiply(num(2, -398), num(5, -1), NE)) == (
        num(1, -398),
        frozenset({Condition.TINY, Condition.QUANTUM}),
    )


QUIET_7 = special(FloatKind.QNAN, False, 7)
SIGNAL_9 = special(FloatKind.SNAN, True, 9)
QUIETED_9 = special(FloatKind.QNAN, True, 9)
INFINITY = special(FloatKind.INFINITY)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_operations_nans_and_comparisons():
    quiet, signaling, quieted = QUIET_7, SIGNAL_9, QUIETED_9

    assert out(dfp_divide(num(0, 0), num(0, 3), NE)) == (
        special(FloatKind.QNAN),
        INVALID,
    )
    assert out(dfp_divide(num(-1, 0), num(0, 0), NE)) == (
        special(FloatKind.INFINITY, True),
        frozenset({Condition.DIVISION_BY_ZERO}),
    )
    assert out(dfp_subtract(INFINITY, INFINITY, NE)) == (
        special(FloatKind.QNAN),
        INVALID,
    )
    assert out(dfp_add(quiet, signaling, NE)) == (quieted, INVALID)
    assert out(dfp_quantize(signaling, quiet, NE)) == (quieted, INVALID)
    assert out(dfp_quantize(special(FloatKind.QNAN, True, 3), quiet, NE)) == (
        quiet,
        NONE,
    )
    assert out(dfp_subtract(num(5, -1), num(50, -2), RoundingMode.TOWARD_NEGATIVE)) == (
        negative_zero(-2),
        NONE,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversions_between_formats_and_fixed_point():
    overflowing = dfp_load_rounded(num(1, 97), SHORT, NE)

    assert dfp_load_rounded(
        special(FloatKind.QNAN, False, 123456789), SHORT, NE
    ).value == DfpValue(SHORT, False, FloatKind.QNAN, 456789)
    assert overflowing.value == DfpValue(SHORT, False, FloatKind.INFINITY)
    assert overflowing.scaled == num(1, 97 - 192)
    assert out(dfp_from_integer(99999999999999995, LONG, NE)) == (
        num(1000000000000000, 2),
        UP_Q,
    )
    assert out(dfp_from_integer(0, LONG, NE)) == (num(0, 0), NONE)
    assert [
        dfp_to_integer(num(25, -1), SIGNED_32, NE),
        dfp_to_integer(num(55, -1), SIGNED_32, RFS),
        dfp_to_integer(num(-25, -1), SIGNED_32, RFS),
        dfp_to_integer(num(1, 10), SIGNED_32, NE),
        dfp_to_integer(special(FloatKind.QNAN), SIGNED_32, NE),
        dfp_to_integer(special(FloatKind.INFINITY, True), SIGNED_32, NE),
    ] == [
        IntegerResult(2, frozenset({Condition.INEXACT})),
        IntegerResult(6, frozenset({Condition.INEXACT, Condition.INCREMENTED})),
        IntegerResult(-2, frozenset({Condition.INEXACT})),
        IntegerResult(2**31 - 1, INVALID),
        IntegerResult(-(2**31), INVALID),
        IntegerResult(-(2**31), INVALID),
    ]
