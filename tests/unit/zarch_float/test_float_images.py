# pyright: standard
"""BFP, HFP and DFP values pack into their images, and exact values round into HFP fractions and DFP formats; images are those the PoO formats give (figures 19-1 to 19-4, chapter 18, figures 20-1 and 20-32), checked against host floats and z390-assembled constants."""

from fractions import Fraction
from pathlib import Path

from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.bfp_bits import long_bits, long_of, short_bits, short_of
from zarch_float.bfp_format import EXTENDED as BFP_EXTENDED
from zarch_float.bfp_format import LONG as BFP_LONG
from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_image import bfp_image
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.dfp_convert import dfp_fitted
from zarch_float.dfp_format import EXTENDED, LONG, SHORT, DfpFormat
from zarch_float.dfp_image import dfp_image
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_format import HfpFormat
from zarch_float.hfp_image import hfp_image
from zarch_float.hfp_rounding import hfp_rounded, hfp_rounded_at
from zarch_float.hfp_value import HfpValue
from zarch_float.rounding_mode import RoundingMode

FIGURE_20_32 = Path(__file__).parents[1] / "hlasm" / "fixtures" / "dpd_figure_20_32.txt"
NE = RoundingMode.NEAREST_EVEN
AWAY = RoundingMode.NEAREST_AWAY
TRUNCATE = RoundingMode.TOWARD_ZERO
UP = RoundingMode.TOWARD_POSITIVE
DOWN = RoundingMode.TOWARD_NEGATIVE
SHORT_BFP_12_BITS = BfpFormat(4, 127, 192)


def _dfp(fmt: DfpFormat, negative: bool, significand: int, exponent: int) -> DfpValue:
    kind = FloatKind.FINITE if significand else FloatKind.ZERO
    return DfpValue(fmt, negative, kind, significand, exponent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bfp_images_pack_every_class_in_any_precision():
    host = [0.1, -2.5, 5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, -0.0]
    assert [bfp_image(long_of(x)) for x in host] == [long_bits(x) for x in host]
    assert bfp_image(short_of(3.5)) == short_bits(3.5)
    assert [
        bfp_image(BfpValue(BFP_LONG, True, FloatKind.INFINITY)),
        bfp_image(BfpValue(BFP_LONG, False, FloatKind.QNAN)),
        bfp_image(BfpValue(BFP_LONG, False, FloatKind.SNAN, 1 << 50)),
        bfp_image(BfpValue(BFP_EXTENDED, False, FloatKind.QNAN, 1 << 110)),
        bfp_image(BfpValue(SHORT_BFP_12_BITS, False, FloatKind.FINITE, 8, -3)),
        bfp_image(BfpValue(SHORT_BFP_12_BITS, True, FloatKind.FINITE, 1, -129)),
    ] == [
        0xFFF0000000000000,
        0x7FF8000000000000,
        0x7FF4000000000000,
        0x7FFFC000000000000000000000000000,
        0x3F8,
        0x801,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hfp_images_take_the_leftmost_bits_of_the_long_or_extended_layout():
    assert [
        hfp_image(HfpValue(HfpFormat(6), False, 0x2E6A3D, 2), 32),
        hfp_image(HfpValue(HfpFormat(28), True, 1 << 108, 1), 128),
        hfp_image(HfpValue(HfpFormat(16), False, 0x199999999999999A, 0), 80),
        hfp_image(HfpValue(HfpFormat(28), False, 1 << 108, -60), 128),
        hfp_image(HfpValue(HfpFormat(1), False, 1, 1), 12),
        hfp_image(HfpValue(HfpFormat(8), False, 0x1999999A, 0), 40),
        hfp_image(HfpValue(HfpFormat(6), True, 0, -64), 32),
        hfp_image(HfpValue(HfpFormat(28), True, 0, -64), 128),
    ] == [
        0x422E6A3D,
        0xC110000000000000B300000000000000,
        0x4019_9999_9999_9999_329A,
        0x04100000000000007600000000000000,
        0x411,
        0x401999999A,
        0x80000000,
        1 << 127,
    ]


def _figure_20_32() -> dict[int, int]:
    rows = FIGURE_20_32.read_text().splitlines()
    return {
        int(row[:2]) * 10 + column: int(declet, 16)
        for row in rows
        for column, declet in enumerate(row.split()[1:])
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfp_images_pack_combination_continuation_and_figure_20_32_declets():
    biased_zero = -SHORT.bias
    assert {
        n: dfp_image(_dfp(SHORT, False, n, biased_zero)) for n in range(1000)
    } == _figure_20_32()
    assert [
        dfp_image(_dfp(SHORT, False, 15, -1)),
        dfp_image(_dfp(LONG, False, 150, -2)),
        dfp_image(_dfp(EXTENDED, True, 1, -3)),
        dfp_image(_dfp(LONG, False, 10**16 - 1, LONG.quantum_max)),
        dfp_image(_dfp(EXTENDED, False, 10**34 - 1, EXTENDED.quantum_max)),
        dfp_image(_dfp(LONG, False, 1, 369)),
        dfp_image(_dfp(SHORT, False, 5_000_000, 48)),
        dfp_image(_dfp(SHORT, False, 9_000_000, 27)),
        dfp_image(_dfp(SHORT, True, 0, 0)),
        dfp_image(DfpValue(SHORT, False, FloatKind.INFINITY)),
        dfp_image(DfpValue(LONG, True, FloatKind.QNAN)),
        dfp_image(DfpValue(SHORT, False, FloatKind.SNAN)),
    ] == [
        0x22400015,
        0x22300000000000D0,
        0xA2074000000000000000000000000001,
        0x77FCFF3FCFF3FCFF,
        0x77FFCFF3FCFF3FCFF3FCFF3FCFF3FCFF,
        0x43FC000000000001,
        0x55500000,
        0x74000000,
        0xA2500000,
        0x78000000,
        0xFC00000000000000,
        0x7E000000,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hfp_rounding_normalizes_scales_carries_and_denormalizes_at_an_exponent():
    tenth = Fraction(1, 10)
    assert [
        hfp_rounded(24, False, tenth, 0, AWAY),
        hfp_rounded(24, False, tenth, 0, TRUNCATE),
        hfp_rounded(24, True, tenth, 0, DOWN),
        hfp_rounded(24, True, tenth, 0, UP),
        hfp_rounded(24, False, Fraction(46415, 1000), 0, AWAY),
        hfp_rounded(24, False, Fraction(1), 2, AWAY),
        hfp_rounded(24, False, Fraction(0xFFFFFF8, 16**7), 0, AWAY),
        hfp_rounded(4, False, Fraction(1), 0, AWAY),
        hfp_rounded(2, False, Fraction(3, 16), 0, AWAY),
        hfp_rounded_at(24, False, Fraction(1, 16**66), -64, AWAY),
    ] == [
        HfpValue(HfpFormat(6), False, 0x19999A, 0),
        HfpValue(HfpFormat(6), False, 0x199999, 0),
        HfpValue(HfpFormat(6), True, 0x19999A, 0),
        HfpValue(HfpFormat(6), True, 0x199999, 0),
        HfpValue(HfpFormat(6), False, 0x2E6A3D, 2),
        HfpValue(HfpFormat(6), False, 0x001000, 3),
        HfpValue(HfpFormat(6), False, 0x100000, 1),
        HfpValue(HfpFormat(1), False, 1, 1),
        HfpValue(HfpFormat(1), False, 0b0100, 0),
        HfpValue(HfpFormat(6), False, 0x010000, -64),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfp_fitting_keeps_the_written_quantum_and_rounds_into_the_format():
    assert [
        dfp_fitted(_dfp(LONG, False, 150, -2), NE).value,
        dfp_fitted(_dfp(SHORT, False, 12345678, -1), NE).value,
        dfp_fitted(
            _dfp(SHORT, False, 12345675, -1), RoundingMode.NEAREST_TOWARD_ZERO
        ).value,
        dfp_fitted(_dfp(SHORT, False, 1, 96), NE).value,
        dfp_fitted(_dfp(SHORT, False, 1, 97), NE).value,
        dfp_fitted(_dfp(SHORT, True, 1, 97), TRUNCATE).value,
        dfp_fitted(_dfp(SHORT, False, 15, -102), NE).value,
        dfp_fitted(_dfp(SHORT, True, 0, -200), NE).value,
    ] == [
        _dfp(LONG, False, 150, -2),
        _dfp(SHORT, False, 1234568, 0),
        _dfp(SHORT, False, 1234567, 0),
        _dfp(SHORT, False, 1_000_000, 90),
        DfpValue(SHORT, False, FloatKind.INFINITY),
        _dfp(SHORT, True, 9_999_999, 90),
        _dfp(SHORT, False, 2, -101),
        _dfp(SHORT, True, 0, -101),
    ]
    assert [
        dfp_fitted(_dfp(SHORT, False, 15, -1), NE).conditions,
        dfp_fitted(_dfp(SHORT, False, 12345678, -1), NE).conditions,
        dfp_fitted(_dfp(SHORT, False, 1, 97), NE).conditions,
        dfp_fitted(_dfp(SHORT, False, 15, -102), NE).conditions,
    ] == [
        frozenset(),
        frozenset({Condition.INEXACT}),
        frozenset({Condition.OVERFLOW, Condition.INEXACT}),
        frozenset({Condition.UNDERFLOW, Condition.TINY, Condition.INEXACT}),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bfp_ties_at_one_bit_of_precision_take_the_even_image():
    one_bit = BfpFormat(1, 127, 192)
    rounding = rounding_into(one_bit, NE)
    assert [
        bfp_image(rounding.round(False, Fraction(3, 2)).value),
        bfp_image(rounding.round(False, Fraction(3)).value),
        bfp_image(rounding.round(True, Fraction(6)).value),
        bfp_image(rounding.round(False, Fraction(1, 2**127)).value),
        bfp_image(rounding_into(one_bit, AWAY).round(False, Fraction(3)).value),
    ] == [0x080, 0x080, 0x182, 0x000, 0x081]
