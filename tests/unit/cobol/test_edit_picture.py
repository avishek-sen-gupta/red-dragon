"""Tests for COBOL numeric edit-picture formatting (edit_picture.py).

Covers the AWS CardDemo subset of numeric editing applied on MOVE into a
numeric-edited receiving item:
  - fixed leading/trailing sign (+/-)
  - zero suppression (Z) with comma blanking in the suppressed zone
  - comma and decimal-point insertion

Expected values follow IBM Enterprise COBOL editing rules.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.edit_picture import (
    UnsupportedEditPictureError,
    format_edited,
    is_numeric_edited,
    parse_edit_picture,
    reject_unsupported,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


class TestIsNumericEdited:
    @covers(CobolFeature.NUMERIC_EDITED)
    def test_plain_numeric_is_not_edited(self):
        assert not is_numeric_edited("9(4)")
        assert not is_numeric_edited("S9(5)V99")
        assert not is_numeric_edited("9(9)V99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_repeat_count_zero_is_not_an_insertion_symbol(self):
        """A '0' inside a repeat count (e.g. the 0 in '9(10)') is a digit count,
        NOT a PIC '0' zero-insertion symbol — so wide plain-numeric pictures
        must not be classified as numeric-edited (red-dragon-r9s9 regression)."""
        assert not is_numeric_edited("9(10)")
        assert not is_numeric_edited("S9(10)V99")
        assert not is_numeric_edited("9(20)")
        assert not is_numeric_edited("9(100)")
        # a genuine trailing '0' insertion is still edited
        assert is_numeric_edited("9(3)09")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_alphanumeric_is_not_edited(self):
        assert not is_numeric_edited("X(8)")
        assert not is_numeric_edited("X(16)")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_sign_and_suppression_pictures_are_edited(self):
        assert is_numeric_edited("+99999999.99")
        assert is_numeric_edited("+9999999999.99")
        assert is_numeric_edited("+ZZZ,ZZZ,ZZZ.99")
        assert is_numeric_edited("-ZZZ,ZZZ,ZZZ.ZZ")
        assert is_numeric_edited("Z(9).99-")


class TestParseEditPicture:
    @covers(CobolFeature.NUMERIC_EDITED)
    def test_width_counts_every_character_position(self):
        # '+' + 8x'9' + '.' + 2x'9' = 12
        assert parse_edit_picture("+99999999.99").width == 12
        # '+' + ZZZ,ZZZ,ZZZ (11) + '.' + '99' (2) = 15
        assert parse_edit_picture("+ZZZ,ZZZ,ZZZ.99").width == 15
        # Z(9) (9) + '.' + '99' + '-' = 13
        assert parse_edit_picture("Z(9).99-").width == 13

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_digit_position_counts(self):
        ep = parse_edit_picture("+99999999.99")
        assert ep.int_digits == 8
        assert ep.frac_digits == 2

        ep2 = parse_edit_picture("+ZZZ,ZZZ,ZZZ.99")
        assert ep2.int_digits == 9
        assert ep2.frac_digits == 2


class TestFormatFixedSignNoSuppression:
    """PIC +99999999.99 — fixed leading sign, all-9, decimal point."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_zero(self):
        assert format_edited("0", "+99999999.99") == "+00000000.00"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_positive(self):
        assert format_edited("12345.67", "+99999999.99") == "+00012345.67"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_negative(self):
        assert format_edited("-12345.67", "+99999999.99") == "-00012345.67"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_truncates_excess_fraction(self):
        # COBOL truncates (no ROUNDED): .679 -> .67
        assert format_edited("1.679", "+99999999.99") == "+00000001.67"


class TestFormatZeroSuppressionWithCommas:
    """PIC +ZZZ,ZZZ,ZZZ.99 — sign, Z suppression, commas, fixed fraction."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_small_positive_suppresses_leading_and_commas(self):
        assert format_edited("1234.56", "+ZZZ,ZZZ,ZZZ.99") == "+      1,234.56"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_zero_suppresses_integer_keeps_fraction(self):
        # Fraction is '99' (not Z) so it always shows; integer all suppressed.
        # Width 15: '+' + 11 suppressed (ZZZ,ZZZ,ZZZ) + '.00'.
        assert format_edited("0", "+ZZZ,ZZZ,ZZZ.99") == "+           .00"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_large_value_fills_all_positions(self):
        assert format_edited("123456789.12", "+ZZZ,ZZZ,ZZZ.99") == "+123,456,789.12"


class TestFormatTrailingSign:
    """PIC Z(9).99- — Z suppression, decimal, trailing minus."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_negative_shows_trailing_minus(self):
        assert format_edited("-123.45", "Z(9).99-") == "      123.45-"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_positive_shows_trailing_space(self):
        assert format_edited("123.45", "Z(9).99-") == "      123.45 "


class TestFormatAllZeroSuppressible:
    """PIC -ZZZ,ZZZ,ZZZ.ZZ — every digit position is Z; zero value blanks all."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_zero_blanks_entire_field(self):
        result = format_edited("0", "-ZZZ,ZZZ,ZZZ.ZZ")
        assert result == " " * 15

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_negative_nonzero_suppresses_only_left_of_decimal(self):
        assert format_edited("-1234.50", "-ZZZ,ZZZ,ZZZ.ZZ") == "-      1,234.50"


class TestInsertionEditSymbols:
    """B / 0 / slash insertion symbols in numeric-edited PIC (red-dragon-r9s9)."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_is_numeric_edited_slash_date(self):
        """PIC 99/99/9999 is recognised as numeric-edited."""
        assert is_numeric_edited("99/99/9999") is True

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_is_numeric_edited_blank_insertion(self):
        """PIC 9(5)BB9 is recognised as numeric-edited."""
        assert is_numeric_edited("9(5)BB9") is True

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_is_numeric_edited_zero_insertion(self):
        """PIC 9(3)09 is recognised as numeric-edited."""
        assert is_numeric_edited("9(3)09") is True

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_format_edited_slash_date(self):
        """format_edited formats a date value into 99/99/9999 template."""
        assert format_edited("12311994", "99/99/9999") == "12/31/1994"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_format_edited_blank_insertion(self):
        """format_edited emits a space for B insertion positions."""
        assert format_edited("123456", "9(5)BB9") == "12345  6"


class TestRejectUnsupported:
    """Unsupported edit symbols are rejected at parse time rather than
    silently mis-formatted (red-dragon-0599).

    Real support for these symbols is red-dragon-5f4g; until then a loud
    failure at field ingestion is the correct resting state, because the
    alternative is well-formed but wrong output (e.g. 'CR' stamped on a
    positive balance) that looks like valid data downstream.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_currency_run_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match=r"\$"):
            reject_unsupported("$$,$$$.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_all_floating_currency_picture_is_rejected(self):
        """The all-float picture that has no 9/Z at all — it never reached
        is_numeric_edited, so it used to die as 'Cannot parse PIC clause'."""
        with pytest.raises(UnsupportedEditPictureError, match=r"\$"):
            reject_unsupported("$$$$.$$")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_currency_written_as_repeat_count_is_rejected(self):
        """'$(4)' is the same floating run as '$$$$' — so the check must run
        on EXPANDED positions, not the raw string."""
        with pytest.raises(UnsupportedEditPictureError, match=r"\$"):
            reject_unsupported("$(4).99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_plus_run_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match=r"\+"):
            reject_unsupported("++++.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_minus_run_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match="-"):
            reject_unsupported("----.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_check_protection_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match=r"\*"):
            reject_unsupported("**,***.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_single_check_protection_symbol_is_rejected(self):
        """Unlike '$', there is no supported single-'*' form."""
        with pytest.raises(UnsupportedEditPictureError, match=r"\*"):
            reject_unsupported("*ZZ9.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_trailing_cr_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match="CR"):
            reject_unsupported("ZZZ.99CR")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_trailing_db_is_rejected(self):
        with pytest.raises(UnsupportedEditPictureError, match="DB"):
            reject_unsupported("ZZ9.99DB")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_error_names_the_offending_picture(self):
        """The message must carry the picture itself — a load-time abort is
        useless if it doesn't say which picture caused it."""
        with pytest.raises(UnsupportedEditPictureError, match=r"\$\$,\$\$\$\.99"):
            reject_unsupported("$$,$$$.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_unsupported_error_is_a_value_error(self):
        """parse_pic has always raised ValueError; subclassing keeps any
        existing except-ValueError handling working."""
        assert issubclass(UnsupportedEditPictureError, ValueError)


class TestRejectUnsupportedAcceptsSupportedPictures:
    """The rejection must not fire on pictures that work correctly today.
    Each of these is a live regression guard, not a smoke test.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_single_fixed_currency_is_accepted(self):
        """A run of ONE '$' is fixed insertion and already formats correctly
        via format_edited's verbatim branch — rejecting it would break
        working code."""
        reject_unsupported("$ZZZ,ZZZ.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_fixed_leading_sign_is_accepted(self):
        reject_unsupported("+99999999.99")
        reject_unsupported("+ZZZ,ZZZ,ZZZ.99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_fixed_trailing_sign_is_accepted(self):
        reject_unsupported("Z(9).99-")
        reject_unsupported("-ZZZ,ZZZ,ZZZ.ZZ")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_trailing_blank_insertion_is_accepted(self):
        """A trailing 'B' is legal blank insertion (supported since
        red-dragon-r9s9) and must not be mistaken for the B of 'DB'."""
        reject_unsupported("ZZ9.99B")
        reject_unsupported("9(5)BB9")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_plain_numeric_pictures_are_accepted(self):
        reject_unsupported("9(4)")
        reject_unsupported("S9(5)V99")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_repeat_count_digits_are_not_scanned_as_symbols(self):
        """red-dragon-r9s9 regression guard: scanning the RAW string once
        made the '0' in '9(10)' look like an insertion symbol. The same
        hazard applies here."""
        reject_unsupported("9(10)")
        reject_unsupported("S9(10)V99")
        reject_unsupported("9(100)")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_alphanumeric_pictures_are_never_rejected(self):
        """X/A pictures can carry these characters in a VALUE literal's
        neighbourhood; they are not numeric-edited and must pass untouched."""
        reject_unsupported("X(22)")
        reject_unsupported("X(8)")
