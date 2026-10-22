# pyright: standard
"""BFP DIVIDE TO INTEGER, TEST DATA CLASS and exact widening against PoO figures 19-22 and 19-26."""

import math

from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.bfp_bits import from_bits, long_of, short_of
from zarch_float.bfp_convert import bfp_widened
from zarch_float.bfp_data_class import bfp_test_data_class
from zarch_float.bfp_divide_to_integer import bfp_divide_to_integer
from zarch_float.bfp_divide_to_integer_result import BfpDivideToIntegerResult
from zarch_float.bfp_format import LONG, SHORT
from zarch_float.bfp_nan import default_nan
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

NE = RoundingMode.NEAREST_EVEN
TZ = RoundingMode.TOWARD_ZERO
AWAY = RoundingMode.NEAREST_AWAY
UP = RoundingMode.TOWARD_POSITIVE
DOWN = RoundingMode.TOWARD_NEGATIVE
INVALID = frozenset({Condition.INVALID})
INF = math.inf
QNAN = BfpValue(LONG, False, FloatKind.QNAN, 5)
SNAN = BfpValue(LONG, True, FloatKind.SNAN, 9)


def _final(remainder: float, quotient: float) -> BfpDivideToIntegerResult:
    return BfpDivideToIntegerResult(
        bfp_exact(long_of(remainder)), long_of(quotient), False, False
    )


def _both(
    value: BfpValue, conditions: frozenset[Condition]
) -> BfpDivideToIntegerResult:
    return BfpDivideToIntegerResult(bfp_exact(value, conditions), value, False, False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_final_quotient_rounds_by_the_modifier_and_signs_follow_figure_19_22():
    cases = [
        (7.0, 2.0, NE, _final(-1.0, 4.0)),
        (7.0, 2.0, TZ, _final(1.0, 3.0)),
        (7.0, 2.0, AWAY, _final(-1.0, 4.0)),
        (-7.0, 2.0, DOWN, _final(1.0, -4.0)),
        (7.0, -2.0, UP, _final(1.0, -3.0)),
        (6.0, 3.0, NE, _final(0.0, 2.0)),
        (-6.0, 3.0, NE, _final(-0.0, -2.0)),
        (1.0, 4.0, NE, _final(1.0, 0.0)),
        (-1.0, 4.0, TZ, _final(-1.0, -0.0)),
        (2.0, INF, NE, _final(2.0, 0.0)),
        (-2.0, INF, NE, _final(-2.0, -0.0)),
        (0.0, 5.0, NE, _final(0.0, 0.0)),
        (-0.0, 5.0, NE, _final(-0.0, -0.0)),
        (0.0, -5.0, NE, _final(0.0, -0.0)),
    ]

    assert [
        bfp_divide_to_integer(long_of(a), long_of(b), mode, NE)
        for a, b, mode, _ in cases
    ] == [expected for *_, expected in cases]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_partial_and_overflowing_quotients_follow_figure_19_22():
    huge = 2.0**127 * (1 + 2.0**-22)

    assert [
        bfp_divide_to_integer(long_of(2.0**60), long_of(3.0), NE, NE),
        bfp_divide_to_integer(long_of(-(2.0**60)), long_of(3.0), UP, NE),
        bfp_divide_to_integer(short_of(2.0**127), short_of(2.0**-126), NE, NE),
        bfp_divide_to_integer(short_of(huge), short_of(3 * 2.0**-126), NE, NE),
        bfp_divide_to_integer(short_of(2.0**-123), short_of(3 * 2.0**-149), NE, NE),
    ] == [
        BfpDivideToIntegerResult(
            bfp_exact(long_of(64.0)), long_of(384307168202282304.0), True, False
        ),
        BfpDivideToIntegerResult(
            bfp_exact(long_of(-64.0)), long_of(-384307168202282304.0), True, False
        ),
        BfpDivideToIntegerResult(
            bfp_exact(short_of(0.0)), short_of(2.0**61), False, True
        ),
        BfpDivideToIntegerResult(
            bfp_exact(short_of(2.0**102)), short_of(768614496750010368.0), True, True
        ),
        BfpDivideToIntegerResult(
            bfp_exact(short_of(2.0**-147)), short_of(22369620.0), True, False
        ),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_operands_and_nans_deliver_one_value_to_both_results():
    quieted = BfpValue(LONG, True, FloatKind.QNAN, 9)

    assert [
        bfp_divide_to_integer(long_of(INF), long_of(2.0), NE, NE),
        bfp_divide_to_integer(long_of(2.0), long_of(0.0), NE, NE),
        bfp_divide_to_integer(long_of(-0.0), long_of(-0.0), NE, NE),
        bfp_divide_to_integer(QNAN, long_of(1.0), NE, NE),
        bfp_divide_to_integer(long_of(1.0), SNAN, NE, NE),
        bfp_divide_to_integer(QNAN, SNAN, NE, NE),
    ] == [
        _both(default_nan(LONG), INVALID),
        _both(default_nan(LONG), INVALID),
        _both(default_nan(LONG), INVALID),
        _both(QNAN, frozenset()),
        _both(quieted, INVALID),
        _both(quieted, INVALID),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_final_remainder_rounds_by_the_fpc_mode_and_reports_tininess():
    inexact = bfp_divide_to_integer(short_of(1.0), short_of(2.0**30), UP, NE)
    tiny = bfp_divide_to_integer(short_of(3 * 2.0**-149), short_of(2.0**-148), NE, NE)
    up = frozenset({Condition.INEXACT, Condition.INCREMENTED})

    assert (inexact, tiny) == (
        BfpDivideToIntegerResult(
            BfpResult(short_of(-(2.0**30)), up, short_of(-(2.0**30)), up),
            short_of(1.0),
            False,
            False,
        ),
        BfpDivideToIntegerResult(
            BfpResult(
                short_of(-(2.0**-149)),
                frozenset({Condition.TINY}),
                short_of(-(2.0**43)),
                frozenset(),
            ),
            short_of(2.0),
            False,
            False,
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_data_class_selects_one_figure_19_26_bit_per_class_and_sign():
    operands = {
        "+0": long_of(0.0),
        "-0": long_of(-0.0),
        "+normal": long_of(1.5),
        "-normal": long_of(-1.5),
        "+subnormal": long_of(5e-324),
        "-subnormal": long_of(-5e-324),
        "+inf": long_of(INF),
        "-inf": long_of(-INF),
        "+qnan": QNAN,
        "-qnan": QNAN.negated(),
        "+snan": SNAN.negated(),
        "-snan": SNAN,
    }

    assert {
        name: [bit for bit in range(52, 64) if bfp_test_data_class(v, 1 << (63 - bit))]
        for name, v in operands.items()
    } == {name: [52 + at] for at, name in enumerate(operands)}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_widening_is_exact_and_keeps_signaling_nans():
    assert [
        bfp_widened(short_of(1.5), LONG),
        bfp_widened(short_of(-(2.0**-149)), LONG),
        bfp_widened(short_of(-INF), LONG),
        bfp_widened(BfpValue(SHORT, False, FloatKind.SNAN, 1), LONG),
        bfp_widened(long_of(-0.0), LONG),
    ] == [
        long_of(1.5),
        long_of(-(2.0**-149)),
        long_of(-INF),
        from_bits(0x7FF00000_20000000, LONG),
        long_of(-0.0),
    ]
