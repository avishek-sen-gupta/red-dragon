"""PIC P decimal scaling (red-dragon-qhtv).

P positions denote decimal scaling: they occupy no storage but shift the
assumed decimal point. The scale convention (see the design doc) is

    trailing P:  scale = +count(P)
    leading  P:  scale = -(count(P) + count(digits))

so `999PP` holding stored digits '009' is the value 900, and `PP9` holding
stored digit '1' is the value .001.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from cobol_asg.pic_parser import parse_pic
from interpreter.cobol.pic_scale import encode_scaled_digits
from tests.covers import covers


class TestScaleIsRecorded:
    @covers(CobolFeature.PIC_CLAUSE)
    @pytest.mark.parametrize(
        ("pic", "scale"),
        [
            ("999PP", 2),
            ("S9PP", 2),
            ("9PP", 2),
            ("PP9", -3),
            ("PP999", -5),
            ("PPP9", -4),
        ],
    )
    def test_scale_from_picture(self, pic: str, scale: int):
        assert parse_pic(pic).scale == scale

    @covers(CobolFeature.PIC_CLAUSE)
    def test_pictures_without_p_have_zero_scale(self):
        for pic in ("9(5)", "S9(5)V99", "X(8)", "$$,$$$.99", "ZZZ.99"):
            assert parse_pic(pic).scale == 0

    @covers(CobolFeature.PIC_CLAUSE)
    def test_leading_and_trailing_p_are_distinguishable(self):
        """These two pictures differ by a factor of 10**7 and returned
        IDENTICAL descriptors before this change."""
        assert parse_pic("999PP") != parse_pic("PP999")

    @covers(CobolFeature.PIC_CLAUSE)
    def test_scaling_does_not_change_byte_width(self):
        """P occupies no storage. The bridge excludes S/V/P from its uniform
        width rule, so Python must agree or record layouts diverge."""
        assert parse_pic("999PP").byte_length == 3
        assert parse_pic("PP999").byte_length == 3
        assert parse_pic("S9PP").byte_length == 1


class TestEncodeAppliesScale:
    """Encoding divides by 10**scale, so the STORED digits are the value's
    significant digits, not the value itself.

    NIST-85 NC124A declares `01 WORK-AREA-30 PICTURE 999PP VALUE 00900.` and
    proves the stored content is '009' by moving it to ZZZPP and asserting
    '  9'.
    """

    @covers(CobolFeature.PIC_CLAUSE)
    @pytest.mark.parametrize(
        ("pic", "value", "stored"),
        [
            ("999PP", "900", "009"),
            ("999PP", "12300", "123"),
            ("999PP", "00900", "009"),
            ("999PP", "950", "009"),
            ("9PP", "200", "2"),
        ],
    )
    def test_stored_digits_are_scaled(self, pic: str, value: str, stored: str):
        assert encode_scaled_digits(value, parse_pic(pic)) == stored

    @covers(CobolFeature.PIC_CLAUSE)
    def test_unscaled_pictures_are_unchanged(self):
        """Regression guard: scale == 0 must leave the digits exactly as the
        pre-change code produced them."""
        assert encode_scaled_digits("12345", parse_pic("9(5)")) == "12345"
        assert encode_scaled_digits("123.45", parse_pic("9(3)V99")) == "12345"

    @covers(CobolFeature.PIC_CLAUSE)
    def test_scaled_division_landing_in_scientific_notation_is_not_corrupted(self):
        """PIC PP9V9 combines leading P (negative scale) with V (decimal
        digits). `Decimal.__truediv__` renders large-magnitude results in
        scientific notation ('1.2E+5'), which `align_decimal` cannot parse —
        it looks for a '.', finds one inside the mantissa, and silently
        drops/zeroes the exponent digits. `format(d, 'f')` must be used
        instead so the digit string stays plain decimal."""
        assert encode_scaled_digits("12", parse_pic("PP9V9")) == "00"


class TestEncodeToleratesNonNumericInput:
    """Before red-dragon-qhtv, every input reaching encode_scaled_digits was
    tolerated (non-digit chars later become 0). Adding the scale >= 0 division
    introduced Decimal(clean), which raises decimal.InvalidOperation on
    non-numeric input (spaces, alphanumeric junk) — a new crash surface,
    confined to the scaled path. Falls back to the pre-existing tolerant
    behaviour instead of crashing."""

    @covers(CobolFeature.PIC_CLAUSE)
    def test_spaces_into_scaled_field_does_not_raise(self):
        encode_scaled_digits("   ", parse_pic("999PP"))

    @covers(CobolFeature.PIC_CLAUSE)
    def test_alphanumeric_junk_into_negative_scaled_field_does_not_raise(self):
        encode_scaled_digits("ABC", parse_pic("PP9"))
