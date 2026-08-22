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
from interpreter.cobol.pic_parser import parse_pic
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
