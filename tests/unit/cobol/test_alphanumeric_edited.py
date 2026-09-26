# pyright: standard
"""Tests for alphanumeric-edited PICTURE support.

An alphanumeric-edited item "can contain the following symbols: A X 9 B 0 /" and
"must contain at least one A or X, and at least one B or 0 (zero) or /" (IBM
Enterprise COBOL for z/OS 6.4 Language Reference, p. 213). On MOVE, the sending
item's characters go into the A / X / 9 positions left to right (right to left
under JUSTIFIED RIGHT) and each B / 0 / '/' position emits its own insertion
character (p. 407, "alphanumeric-edited receiving item").
"""

from __future__ import annotations

import pytest

from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.edit_picture import format_alphanumeric_edited
from interpreter.cobol.features import CobolFeature
from cobol_asg.pic_parser import parse_pic
from tests.covers import FeatureStatus, covers


class TestDescriptor:
    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_category_and_size(self):
        desc = parse_pic("XXBXXBXX")
        assert desc.category == CobolDataCategory.ALPHANUMERIC_EDITED
        assert desc.char_positions == 8
        assert desc.byte_length == 8
        assert desc.pic_string == "XXBXXBXX"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_insertion_positions_are_bytes_not_digits(self):
        # Every position is a byte, insertion characters included: the record
        # width the bridge allocates must agree (red-dragon-ilb6).
        assert parse_pic("X(26)BX(12)0X(10)").byte_length == 50
        assert parse_pic("A/AA").byte_length == 4


class TestFormatting:
    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_blank_insertion(self):
        assert format_alphanumeric_edited("ABCDEF", "XXBXXBXX") == "AB CD EF"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_slash_insertion(self):
        assert format_alphanumeric_edited("ABCD", "XX/XX") == "AB/CD"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_zero_insertion(self):
        assert format_alphanumeric_edited("1234", "XXBX0X") == "12 304"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_a_and_nine_positions_both_receive_data(self):
        # In this category 9 is a data position like A and X, not a digit that
        # forces numeric content.
        assert format_alphanumeric_edited("XY", "A/A") == "X/Y"
        assert format_alphanumeric_edited("AB12", "XXB99") == "AB 12"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_short_sender_is_space_filled_on_the_right(self):
        assert format_alphanumeric_edited("A", "XXBXX") == "A    "

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_long_sender_is_truncated_on_the_right(self):
        assert format_alphanumeric_edited("ABCDEFGH", "XXBXX") == "AB CD"

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_repeat_counts_are_expanded(self):
        assert format_alphanumeric_edited("ABCDEFG", "X(3)BX(4)") == "ABC DEFG"

    @covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.JUSTIFIED_CLAUSE)
    def test_justified_right_fills_and_truncates_on_the_left(self):
        assert format_alphanumeric_edited("AB", "XXBXX", justified_right=True) == (
            "   AB"
        )
        assert format_alphanumeric_edited(
            "ABCDEFGH", "XXBXX", justified_right=True
        ) == ("EF GH")


class TestExternalFloatingPointStaysRefused:
    """The other category the grammar recognises and the runtime cannot store.

    Unlike alphanumeric-edited it needs an encoder and a decoder of its own for
    the display float form, not just a MOVE-time formatter, so it is still
    refused at field ingestion (red-dragon-0599's stance).
    """

    @covers(CobolFeature.EXTERNAL_FLOATING_POINT, status=FeatureStatus.UNSUPPORTED)
    def test_external_float_is_refused(self):
        from cobol_asg.edit_picture import UnsupportedEditPictureError

        with pytest.raises(
            UnsupportedEditPictureError, match="external floating-point"
        ):
            parse_pic("+999.99E+99")
