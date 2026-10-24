# pyright: standard
"""HFP arithmetic: guard digit, truncation, rounding and exponent conditions per the PoO."""

from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.hfp_bits import image, long, short
from zarch_float.bfp_format import LONG as BFP_LONG
from zarch_float.bfp_format import SHORT as BFP_SHORT
from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_image import bfp_image
from zarch_float.comparison import Comparison
from zarch_float.comparison_result import ComparisonResult
from zarch_float.condition import Condition
from zarch_float.hfp_arithmetic import (
    hfp_add,
    hfp_compare,
    hfp_divide,
    hfp_halve,
    hfp_load_fp_integer,
    hfp_multiply,
    hfp_multiply_add,
    hfp_multiply_add_unnormalized,
    hfp_multiply_subtract,
    hfp_multiply_unnormalized,
    hfp_square_root,
    hfp_subtract,
)
from zarch_float.hfp_convert import (
    hfp_to_bfp,
    hfp_to_integer,
)
from zarch_float.hfp_format import EXTENDED, LONG, SHORT
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_value import HfpValue
from zarch_float.integer_format import SIGNED_32
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import HFP_TO_BFP_MODIFIER_MODES, RoundingMode

NONE: frozenset[Condition] = frozenset()
OVERFLOW = frozenset({Condition.HFP_EXPONENT_OVERFLOW})
UNDERFLOW = frozenset({Condition.HFP_EXPONENT_UNDERFLOW})
SIGNIFICANCE = frozenset({Condition.HFP_SIGNIFICANCE})


def _out(result: HfpResult) -> tuple[int, frozenset[Condition]]:
    return image(result.value), result.conditions


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_square_root_follows_the_sqer_examples():
    examples = {0x42190000: 0x41500000, 0x40400000: 0x40800000, 0x40800000: 0x40B504F3}
    examples_with_odd_exponent = {0x41800000: 0x412D413D}

    assert {
        x: _out(hfp_square_root(short(x)))
        for x in {**examples, **examples_with_odd_exponent}
    } == {x: (y, NONE) for x, y in {**examples, **examples_with_odd_exponent}.items()}
    assert _out(hfp_square_root(short(0xC1100000))) == (
        0xC1100000,
        frozenset({Condition.HFP_SQUARE_ROOT}),
    )
    assert _out(hfp_square_root(short(0xC5000000))) == (0x00000000, NONE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_addition_keeps_one_guard_digit_and_normalizes_on_request():
    one, just_below_one = short(0x41100000), short(0x40FFFFFF)

    assert _out(hfp_subtract(one, just_below_one, True)) == (0x3B100000, NONE)
    assert _out(hfp_subtract(one, just_below_one, False)) == (0x41000000, SIGNIFICANCE)
    assert _out(hfp_add(short(0x42001000), short(0x42000100), False)) == (
        0x42001100,
        NONE,
    )
    assert _out(hfp_add(short(0x42001000), short(0x42000100), True)) == (
        0x40110000,
        NONE,
    )
    assert _out(hfp_add(short(0x41F00000), short(0x41200000), True)) == (
        0x42110000,
        NONE,
    )
    assert _out(hfp_add(short(0x7FF00000), short(0x7F200000), False)) == (
        0x00110000,
        OVERFLOW,
    )
    assert _out(hfp_subtract(short(0x00100000), short(0x000F0000), True)) == (
        0x7F100000,
        UNDERFLOW,
    )
    assert _out(hfp_subtract(short(0xC3123456), short(0xC3123456), True)) == (
        0x43000000,
        SIGNIFICANCE,
    )
    assert [
        hfp_compare(one, just_below_one),
        hfp_compare(short(0x42000000), short(0x40000001)),
        hfp_compare(short(0xC1100000), short(0x41100000)),
        hfp_compare(short(0x80000000), short(0x7F000000)),
    ] == [
        ComparisonResult(Comparison.HIGH, NONE),
        ComparisonResult(Comparison.EQUAL, NONE),
        ComparisonResult(Comparison.LOW, NONE),
        ComparisonResult(Comparison.EQUAL, NONE),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiply_divide_and_halve_truncate_exact_intermediates():
    three, third = short(0x41300000), short(0x40555556)

    assert _out(hfp_multiply(three, third, SHORT)) == (0x41100000, NONE)
    assert hfp_multiply(three, third, LONG).value == long(0x4110000020000000)
    assert _out(hfp_divide(short(0x41100000), three)) == (0x40555555, NONE)
    assert _out(hfp_halve(short(0x41100001))) == (0x40800008, NONE)
    assert _out(hfp_divide(three, short(0x41000000))) == (
        0x41300000,
        frozenset({Condition.HFP_DIVIDE}),
    )
    assert [
        _out(hfp_divide(short(0x80000000), three)),
        _out(hfp_multiply(short(0xC5000000), three, SHORT)),
    ] == [(0x00000000, NONE), (0x00000000, NONE)]
    assert _out(hfp_multiply(short(0x01100000), short(0x01100000), SHORT)) == (
        0x41100000,
        UNDERFLOW,
    )
    assert _out(hfp_multiply(short(0x7F100000), short(0x7F100000), SHORT)) == (
        0x3D100000,
        OVERFLOW,
    )
    assert hfp_multiply(
        long(0x4110000000000001), long(0x4110000000000001), EXTENDED
    ) == (HfpResult(HfpValue(EXTENDED, False, 0x1000000000000200000000000010, 1), NONE))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_integer_rounds_by_the_method_and_clamps_out_of_range():
    nearest_even, nearest_away = RoundingMode.NEAREST_EVEN, RoundingMode.NEAREST_AWAY
    two_and_a_half = short(0x41280000)

    assert [
        hfp_to_integer(two_and_a_half, SIGNED_32, nearest_even),
        hfp_to_integer(two_and_a_half, SIGNED_32, nearest_away),
        hfp_to_integer(short(0xC1280000), SIGNED_32, RoundingMode.TOWARD_NEGATIVE),
        hfp_to_integer(short(0x3F100000), SIGNED_32, RoundingMode.TOWARD_POSITIVE),
        hfp_to_integer(short(0xC9100000), SIGNED_32, nearest_even),
    ] == [
        IntegerResult(2, NONE),
        IntegerResult(3, NONE),
        IntegerResult(-3, NONE),
        IntegerResult(1, NONE),
        IntegerResult(-(2**31), frozenset({Condition.OUT_OF_RANGE})),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_fp_integer_truncates_normalizes_and_makes_zero_positive():
    two_and_a_half_and_a_little = (0x28 << 104) | 1

    assert [
        _out(hfp_load_fp_integer(short(x)))
        for x in (
            0x41180000,
            0xC1280000,
            0x40800000,
            0xC0800000,
            0x43001000,
            0x47123456,
        )
    ] == [
        (0x41100000, NONE),
        (0xC1200000, NONE),
        (0x00000000, NONE),
        (0x00000000, NONE),
        (0x41100000, NONE),
        (0x47123456, NONE),
    ]
    assert hfp_load_fp_integer(
        HfpValue(EXTENDED, False, two_and_a_half_and_a_little, 1)
    ) == HfpResult(HfpValue(EXTENDED, False, 0x2 << 108, 1), NONE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiply_add_keeps_the_exact_product_and_truncates_once():
    below_one = short(0x40FFFFFF)

    assert [
        _out(hfp_multiply_add(short(0x41200000), short(0x41300000), short(0x41100000))),
        _out(hfp_multiply_subtract(below_one, below_one, short(0x40FFFFFE))),
        _out(hfp_multiply_add(short(0x41200000), short(0x41300000), short(0xC1600000))),
        _out(hfp_multiply_add(short(0x7F100000), short(0x7F100000), short(0))),
        _out(hfp_multiply_subtract(short(0x01100000), short(0x01100000), short(0))),
    ] == [
        (0x41700000, NONE),
        (0x35100000, NONE),
        (0x00000000, NONE),
        (0x3D100000, OVERFLOW),
        (0x41100000, UNDERFLOW),
    ]
    assert hfp_multiply_add(
        long(0x41200000_00000000), long(0x41300000_00000000), long(0xC1100000_00000000)
    ) == HfpResult(long(0x41500000_00000000), NONE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unnormalized_multiplies_keep_the_28_digit_window_unwrapped():
    one, two = long(0x4110000000000000), long(0x4120000000000000)
    top = 2 << 104

    assert [
        hfp_multiply_unnormalized(one, two),
        hfp_multiply_unnormalized(long(0xC100000000000000), two),
        hfp_multiply_unnormalized(long(0x7F10000000000000), long(0x7F10000000000000)),
    ] == [
        HfpResult(HfpValue(EXTENDED, False, top, 2), NONE),
        HfpResult(HfpValue(EXTENDED, True, 0, 2), NONE),
        HfpResult(HfpValue(EXTENDED, False, 1 << 104, 126), NONE),
    ]
    assert [
        hfp_multiply_add_unnormalized(one, two, long(c)).value
        for c in (
            0x4130000000000000,
            0x4810000000000000,
            0xA110000000000000,
            0xC120000000000000,
            0xC130000000000000,
        )
    ] == [
        HfpValue(EXTENDED, False, 5 << 104, 2),
        HfpValue(EXTENDED, False, top, 2),
        HfpValue(EXTENDED, False, top - 1, 2),
        HfpValue(EXTENDED, False, 0, 2),
        HfpValue(EXTENDED, True, 1 << 104, 2),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hfp_to_bfp_rounds_by_the_modifier_denormalizes_and_overflows_per_figure_9_20():
    modes = HFP_TO_BFP_MODIFIER_MODES

    def converted(bits: int, target: BfpFormat, m3: int) -> tuple[int, bool]:
        result = hfp_to_bfp(long(bits), target, modes[m3])
        return bfp_image(result.value), Condition.OVERFLOW in result.conditions

    assert sorted(modes) == [0, 1, 3, 4, 5, 6, 7]
    assert [
        converted(0x4110000000000000, BFP_SHORT, 4),
        converted(0x4055555555555555, BFP_SHORT, 4),
        converted(0x4055555555555555, BFP_SHORT, 0),
        converted(0x4055555555555555, BFP_SHORT, 3),
        converted(0x8000000000000000, BFP_SHORT, 4),
        converted(0xC500000000000000, BFP_LONG, 1),
        converted(0x1E10000000000000, BFP_SHORT, 4),
        converted(0x1910000000000000, BFP_SHORT, 4),
        converted(0x9910000000000000, BFP_SHORT, 7),
        converted(0x7F10000000000000, BFP_SHORT, 1),
        converted(0x7F10000000000000, BFP_SHORT, 5),
        converted(0x7F10000000000000, BFP_SHORT, 3),
        converted(0xFF10000000000000, BFP_SHORT, 6),
        converted(0xFF10000000000000, BFP_SHORT, 7),
        converted(0x41FFFFFFFFFFFFFF, BFP_LONG, 4),
        converted(0x41FFFFFFFFFFFFFF, BFP_LONG, 5),
        converted(0x7FFFFFFFFFFFFFFF, BFP_LONG, 4),
    ] == [
        (0x3F800000, False),
        (0x3EAAAAAB, False),
        (0x3EAAAAAA, False),
        (0x3EAAAAAB, False),
        (0x80000000, False),
        (0x8000000000000000, False),
        (0x00000200, False),
        (0x00000000, False),
        (0x80000001, False),
        (0x7F800000, True),
        (0x7F7FFFFF, True),
        (0x7F7FFFFF, True),
        (0xFF7FFFFF, True),
        (0xFF800000, True),
        (0x4030000000000000, False),
        (0x402FFFFFFFFFFFFF, False),
        (0x4FB0000000000000, False),
    ]
