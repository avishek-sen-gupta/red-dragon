"""Numeric edit-picture conformance tests, transcribed from the NIST-85 suite.

Every case below is a (PICTURE, value, expected) triple lifted from the COBOL-85
conformance programs vendored at
``proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/``:

  - NC124A.CBL — the dedicated PICTURE editing program (floating currency,
    floating sign, check protection, Z suppression)
  - NC105A.CBL — edited MOVE, including the trailing CR / DB report symbols

These are the standard's own expected values, not a reading of the rules, which
matters because several of them contradict the obvious generalisation of the
existing Z-suppression code. In particular '*' does NOT blank a zero field the
way Z does, and it preserves the decimal point (red-dragon-5f4g).

The values are transcribed as literals rather than parsed from the .CBL at run
time so the expectations are reviewable in the diff. Each NIST WORK-AREA holds
its value without truncation, so the literal here is the true numeric input.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.edit_picture import format_edited
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.pic_parser import parse_pic
from tests.covers import covers


class TestNistFloatingCurrency:
    """Floating currency insertion, verified against NIST-85 NC124A.CBL.

    The '$' is not at a fixed position: it is emitted immediately to the
    left of the first significant digit, so it slides with the value.
    A run of N float symbols is N-1 digit positions plus one reserved for
    the symbol itself, and the run may have ',' / '.' interspersed
    ("$$,$$$.$$" is ONE floating string of seven '$', not three runs)."""

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("value", "pic", "expected"),
        [
            ("0", "$$99", " $00"),
            ("0", "$$$$9", "   $0"),
            ("0", "$$$$$.99", "    $.00"),
            ("0", "$$,$$$.$$", "         "),
            (".02", "$$99", " $00"),
            (".02", "$$$$9", "   $0"),
            (".02", "$$$$$.99", "    $.02"),
            (".02", "$$,$$$.$$", "     $.02"),
            ("12", "$$99", " $12"),
            ("12", "$$$$9", "  $12"),
            ("12", "$$$$$.99", "  $12.00"),
            ("12", "$$,$$$.$$", "   $12.00"),
            ("12.34", "$$99", " $12"),
            ("12.34", "$$$$9", "  $12"),
            ("12.34", "$$$$$.99", "  $12.34"),
            ("12.34", "$$,$$$.$$", "   $12.34"),
            ("1234", "$$99", "$234"),
            ("1234", "$$$$9", "$1234"),
            ("1234", "$$$$$.99", "$1234.00"),
            ("1234", "$$,$$$.$$", "$1,234.00"),
            ("1234.56", "$$99", "$234"),
            ("1234.56", "$$$$9", "$1234"),
            ("1234.56", "$$$$$.99", "$1234.56"),
            ("1234.56", "$$,$$$.$$", "$1,234.56"),
        ],
    )
    def test_matches_nist(self, value: str, pic: str, expected: str):
        assert format_edited(value, pic) == expected


class TestNistFloatingSign:
    """Floating sign insertion (++++ / ----), verified against NIST-85 NC124A.CBL.

    '+' emits '+' when non-negative and '-' when negative; '-' emits a
    space when non-negative and '-' when negative — the same polarity as
    the existing FIXED sign, but floated to the first significant digit."""

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("value", "pic", "expected"),
        [
            ("0", "++++9", "   +0"),
            ("0", "----9", "    0"),
            ("0", "+++++", "     "),
            # NIST compares this 5-char field against a SIX-space literal.
            # That passes in COBOL, whose comparison space-pads the shorter
            # operand, but it is a typo: every other expectation for this
            # picture is 5 chars. Normalised to the picture width.
            ("0", "-----", "     "),
            ("0", "+++++.++", "        "),
            ("0", "--,---.--", "         "),
            ("12", "++++9", "  +12"),
            ("12", "----9", "   12"),
            ("12", "+++++", "  +12"),
            ("12", "-----", "   12"),
            ("12", "+++++.++", "  +12.00"),
            ("12", "--,---.--", "    12.00"),
            ("-12", "++++9", "  -12"),
            ("-12", "----9", "  -12"),
            ("-12", "+++++", "  -12"),
            ("-12", "-----", "  -12"),
            ("-12", "+++++.++", "  -12.00"),
            ("-12", "--,---.--", "   -12.00"),
            ("123", "++++9", " +123"),
            ("123", "----9", "  123"),
            ("123", "+++++", " +123"),
            ("123", "-----", "  123"),
            ("123", "+++++.++", " +123.00"),
            ("123", "--,---.--", "   123.00"),
            ("-123", "++++9", " -123"),
            ("-123", "----9", " -123"),
            ("-123", "+++++", " -123"),
            ("-123", "-----", " -123"),
            ("-123", "+++++.++", " -123.00"),
            ("-123", "--,---.--", "  -123.00"),
            ("1234", "++++9", "+1234"),
            ("1234", "----9", " 1234"),
            ("1234", "+++++", "+1234"),
            ("1234", "-----", " 1234"),
            ("1234", "+++++.++", "+1234.00"),
            ("1234", "--,---.--", " 1,234.00"),
            ("-1234", "++++9", "-1234"),
            ("-1234", "----9", "-1234"),
            ("-1234", "+++++", "-1234"),
            ("-1234", "-----", "-1234"),
            ("-1234", "+++++.++", "-1234.00"),
            ("-1234", "--,---.--", "-1,234.00"),
            ("12.34", "++++9", "  +12"),
            ("12.34", "----9", "   12"),
            ("12.34", "+++++", "  +12"),
            ("12.34", "-----", "   12"),
            ("12.34", "+++++.++", "  +12.34"),
            ("12.34", "--,---.--", "    12.34"),
            ("-12.34", "++++9", "  -12"),
            ("-12.34", "----9", "  -12"),
            ("-12.34", "+++++", "  -12"),
            ("-12.34", "-----", "  -12"),
            ("-12.34", "+++++.++", "  -12.34"),
            ("-12.34", "--,---.--", "   -12.34"),
        ],
    )
    def test_matches_nist(self, value: str, pic: str, expected: str):
        assert format_edited(value, pic) == expected


class TestNistCheckProtection:
    """Asterisk check protection, verified against NIST-85 NC124A.CBL.

    '*' is zero suppression with '*' as the fill character instead of a
    space — but with one critical divergence from Z: a zero value does NOT
    blank the field. "**.**" at zero is '**.**', and "*,***.**" is
    '*****.**' — the comma becomes '*' while the DECIMAL POINT SURVIVES.
    Compare "ZZ.ZZ" at zero, which blanks to five spaces, point included."""

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("value", "pic", "expected"),
        [
            ("0", "*999", "*000"),
            ("0", "**99", "**00"),
            ("0", "***9", "***0"),
            ("0", "**.**", "**.**"),
            ("0", "*,***.**", "*****.**"),
            ("13", "*999", "*013"),
            ("13", "**99", "**13"),
            ("13", "***9", "**13"),
            ("13", "**.**", "13.00"),
            ("13", "*,***.**", "***13.00"),
            ("123", "*999", "*123"),
            ("123", "**99", "*123"),
            ("123", "***9", "*123"),
            ("123", "**.**", "23.00"),
            ("123", "*,***.**", "**123.00"),
            ("2010", "*999", "2010"),
            ("2010", "**99", "2010"),
            ("2010", "***9", "2010"),
            ("2010", "**.**", "10.00"),
            ("2010", "*,***.**", "2,010.00"),
            ("1010.2", "*999", "1010"),
            ("1010.2", "**99", "1010"),
            ("1010.2", "***9", "1010"),
            ("1010.2", "**.**", "10.20"),
            ("1010.2", "*,***.**", "1,010.20"),
            (".01", "*999", "*000"),
            (".01", "**99", "**00"),
            (".01", "***9", "***0"),
            (".01", "**.**", "**.01"),
            (".01", "*,***.**", "*****.01"),
        ],
    )
    def test_matches_nist(self, value: str, pic: str, expected: str):
        assert format_edited(value, pic) == expected


class TestNistTrailingSignCrDb:
    """Trailing CR / DB, verified against NIST-85 NC105A.CBL.

    CR and DB are a single two-character trailing token occupying two bytes.
    They are emitted ONLY when the value is negative; a non-negative value
    emits two spaces. Emitting them unconditionally (the pre-fix behaviour)
    reported a credit on every positive balance.

    They must be lexed as one token before per-character dispatch, or the
    'B' of 'DB' is consumed by the B blank-insertion branch (red-dragon-r9s9)
    and the field renders as 'D '.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("value", "pic", "expected"),
        [
            ("-12345", "9(5)DB", "12345DB"),
            ("12345", "9(5)DB", "12345  "),
            ("-12345", "9(5)CR", "12345CR"),
            ("12345", "9(5)CR", "12345  "),
        ],
    )
    def test_matches_nist(self, value: str, pic: str, expected: str):
        assert format_edited(value, pic) == expected


class TestParsePicAcceptsImplementedSymbols:
    """The symbols red-dragon-0599 rejected are now implemented, so parse_pic
    must ACCEPT them and size them by character width.

    0599 rejected these deliberately, as a safe resting state while they were
    unimplemented. That rejection is what this class replaces — the guard is
    no longer protecting anything, it is blocking a working feature.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("pic", "width"),
        [
            ("$$,$$$.99", 9),
            ("$$$$.$$", 7),
            ("**,***.99", 9),
            ("ZZZ.99CR", 8),
            ("ZZ9.99DB", 8),
            ("++++.99", 7),
            ("----.99", 7),
            ("$(4).99", 7),
        ],
    )
    def test_parse_pic_accepts_and_sizes(self, pic: str, width: int):
        descriptor = parse_pic(pic)
        assert descriptor.category == CobolDataCategory.NUMERIC_EDITED
        assert descriptor.byte_length == width

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_single_fixed_currency_still_accepted(self):
        """A run of one is fixed insertion and always worked; the floating
        implementation must not have disturbed it."""
        assert format_edited("1234.5", "$ZZZ,ZZZ.99") == "$  1,234.50"


class TestScalingPositionsAreNotStored:
    """S, V and P occupy no storage, so an edited picture containing them must
    not count them toward its byte width (red-dragon-ilb6 follow-up).

    The bridge computes record OFFSETS with a uniform rule that excludes
    S/V/P, while parse_edit_picture sized by raw character count. For
    'PIC ZZZPP' the bridge allocated 3 bytes and Python read 5 — reading two
    bytes into the next field, with nothing raising. Before ilb6 both sides
    said 5 (wrong, but agreeing); ilb6 corrected the bridge and exposed the
    Python half.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("pic", "width"),
        [
            ("ZZZPP", 3),
            ("ZZZ", 3),
            ("ZZZV99", 5),
            ("+ZZZ,ZZZ,ZZZ.99", 15),
            ("$$,$$$.99", 9),
        ],
    )
    def test_byte_length_excludes_scaling_positions(self, pic: str, width: int):
        assert parse_pic(pic).byte_length == width
