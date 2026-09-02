# pyright: standard
"""Tests for the full PICTURE character-string grammar.

The parser no longer classifies a picture by symbol-set membership before
parsing: the category is whichever top-level alternative of picture.lark parses.
These tests assert the categories, the Table 12 sizes, and the spec rules that
are enforced by the semantic pass rather than by the grammar.

Spec references are to IBM Enterprise COBOL for z/OS 6.4 Language Reference.
"""

from __future__ import annotations

import pytest

from cobol_asg import picture
from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.edit_picture import UnsupportedEditPictureError
from interpreter.cobol.features import CobolFeature
from cobol_asg.pic_parser import parse_pic
from tests.covers import FeatureStatus, covers


class TestCategoryComesFromTheParse:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_alphabetic_is_stored_as_alphanumeric(self):
        # "The PICTURE character-string can contain only the symbol A" (p. 213).
        # The grammar tells alphabetic apart from alphanumeric; the descriptor
        # does not, because the two are stored and moved identically here.
        assert picture.analyse(picture.build_parser().parse("A(5)")).category == (
            "alphabetic"
        )
        desc = parse_pic("A(5)")
        assert desc.category == CobolDataCategory.ALPHANUMERIC
        assert desc.char_positions == 5
        assert desc.byte_length == 5

    @covers(CobolFeature.PIC_CLAUSE)
    def test_alphanumeric_mixing_a_and_9(self):
        # "combinations of the symbols A, X, and 9. (A character-string containing
        # all As or all 9s does not define an alphanumeric item.)" (p. 213).
        desc = parse_pic("AAA9")
        assert desc.category == CobolDataCategory.ALPHANUMERIC
        assert desc.char_positions == 4
        assert desc.byte_length == 4

    @covers(CobolFeature.PIC_CLAUSE)
    def test_numeric_is_categorised_by_usage_not_by_the_picture(self):
        assert parse_pic("S9(5)V99").category == CobolDataCategory.ZONED_DECIMAL
        assert parse_pic("S9(5)V99", usage="COMP-3").category == CobolDataCategory.COMP3

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_fixed_currency_before_zero_suppression_is_legal(self):
        # The p. 224 exclusion is between FLOATING symbols; a single fixed
        # currency symbol ahead of a suppression run is fine.
        desc = parse_pic("$ZZ,ZZ9")
        assert desc.category == CobolDataCategory.NUMERIC_EDITED
        assert desc.char_positions == 7
        assert desc.byte_length == 7

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_currency_run_is_one_fewer_digit_than_its_length(self):
        # "The second leftmost floating insertion symbol ... represents the
        # leftmost limit at which numeric data can appear" (p. 223).
        desc = parse_pic("$,$$$,999.99")
        assert desc.category == CobolDataCategory.NUMERIC_EDITED
        assert desc.char_positions == 12
        assert desc.decimal_digits == 2

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_zero_suppression_counts_every_symbol_as_a_digit(self):
        # "Each Z ... a leading numeric character position" (Table 12, p. 210).
        desc = parse_pic("ZZZZ.ZZ")
        assert desc.category == CobolDataCategory.NUMERIC_EDITED
        assert desc.char_positions == 7
        assert desc.decimal_digits == 2


class TestTableTwelveSizes:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_scaling_positions_are_digits_but_not_stored(self):
        # "P ... Not counted in the size of the data item. Scaling position
        # characters are counted in determining the maximum number of digit
        # positions" (Table 12, p. 209). The analysis reports both; a zoned
        # descriptor keeps only the stored digits, since its encoders write one
        # byte per digit and P has no byte.
        analysis = picture.analyse(picture.build_parser().parse("PPP999"))
        assert analysis.digit_positions == 6
        assert analysis.scaling_positions == 3
        assert analysis.char_positions == 3
        # The point is not WRITTEN, so no digit is a fraction digit; the shift
        # the leading Ps imply is reported as point_shift instead.
        assert analysis.fraction_digits == 0
        assert analysis.point_shift == -6

        desc = parse_pic("PPP999")
        assert desc.category == CobolDataCategory.ZONED_DECIMAL
        assert desc.total_digits == 3
        assert desc.char_positions == 3
        assert desc.byte_length == 3

    @covers(CobolFeature.USAGE_COMP_3)
    def test_scaling_positions_are_excluded_from_packed_decimal_size_too(self):
        # A scaling position holds no digit in any USAGE: PPP999 stores the three
        # digits written as 9, and the Ps become the descriptor's scale
        # (red-dragon-qhtv). So packed storage is three digits in (3 // 2) + 1
        # bytes, and the bridge's uniform rule excludes P for the same reason.
        desc = parse_pic("PPP999", usage="COMP-3")
        assert desc.total_digits == 3
        assert desc.scale == -6
        assert desc.byte_length == 2

    @covers(CobolFeature.PIC_CLAUSE)
    def test_a_picture_of_only_scaling_positions_stores_nothing(self):
        # NIST IX110A: 01 STATUS-TEST-10 PIC P VALUE ZERO (red-dragon-m0oa.2).
        desc = parse_pic("P")
        assert desc.category == CobolDataCategory.ZONED_DECIMAL
        assert desc.total_digits == 0
        assert desc.char_positions == 0
        assert desc.byte_length == 0

    @covers(CobolFeature.SIGN_CLAUSE)
    def test_sign_separate_adds_a_character_position(self):
        # "S ... Not counted in the size of the elementary item unless an
        # associated SIGN clause specifies the SEPARATE CHARACTER phrase"
        # (Table 12, p. 210).
        assert parse_pic("S9(5)").char_positions == 5
        assert parse_pic("S9(5)", sign_separate=True).char_positions == 6
        assert parse_pic("S9(5)", sign_separate=True).byte_length == 6

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_cr_occupies_two_character_positions(self):
        # "Each character used in the editing sign control symbol is counted"
        # (Table 12, p. 210).
        assert parse_pic("ZZZ.99CR").char_positions == 8
        assert parse_pic("ZZZ.99CR").byte_length == 8


class TestRulesTheGrammarCannotEnforce:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_too_many_digit_positions_raises(self):
        # "the number of digit positions represented in the character-string
        # must be in the range 1 through 18, inclusive" under ARITH(COMPAT)
        # (p. 217).
        with pytest.raises(ValueError, match="19 digit positions, must be 1 to 18"):
            parse_pic("9(19)")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_two_editing_sign_symbols_raise(self):
        # "Only one of the following symbols can be written in a given PICTURE
        # character-string: + - CR DB" (p. 218).
        with pytest.raises(ValueError, match=r"more than one of \+ - CR DB"):
            parse_pic("+999+")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_currency_and_zero_suppression_are_exclusive(self):
        # "The following symbols are mutually exclusive as floating replacement
        # symbols in one PICTURE character-string: Z * + - cs" (p. 224).
        with pytest.raises(ValueError, match="mutually exclusive"):
            parse_pic("$$$ZZ9")

    @covers(CobolFeature.PIC_CLAUSE)
    def test_a_string_that_is_no_picture_at_all_raises(self):
        with pytest.raises(ValueError, match="Cannot parse PIC clause"):
            parse_pic("9(5)Q")


class TestCategoriesWithoutRuntimeSupport:
    """The category the grammar recognises but the runtime cannot represent.

    Refused at field ingestion rather than accepted and mis-stored, the same
    stance red-dragon-0599 took for edit symbols the formatter could not honour.
    Alphanumeric-edited was refused here too until its MOVE-time insertion was
    implemented — see tests/unit/cobol/test_alphanumeric_edited.py.
    """

    @covers(CobolFeature.ALPHANUMERIC_EDITED)
    def test_alphanumeric_edited_is_sized_by_character_positions(self):
        desc = parse_pic("X(8)B(3)")
        assert desc.category == CobolDataCategory.ALPHANUMERIC_EDITED
        assert desc.byte_length == 11

    @covers(CobolFeature.EXTERNAL_FLOATING_POINT, status=FeatureStatus.UNSUPPORTED)
    def test_external_floating_point_is_refused(self):
        with pytest.raises(
            UnsupportedEditPictureError, match="external floating-point"
        ):
            parse_pic("+999.99E+99")


class TestSpecialNamesTemplate:
    """The three SPECIAL-NAMES-dependent terminals are substituted per unit.

    parse_pic itself still uses the default "$" and "." (threading SPECIAL-NAMES
    from the compilation unit into field ingestion is not done).
    """

    @covers(CobolFeature.PIC_CLAUSE)
    def test_decimal_point_is_comma_swaps_the_two_symbols(self):
        parser = picture.build_parser(decimal_point_is_comma=True)
        analysis = picture.analyse(parser.parse("ZZZ.ZZZ,99"))
        assert analysis.category == "numeric_edited"
        assert analysis.char_positions == 10
        assert analysis.fraction_digits == 2

    @covers(CobolFeature.PIC_CLAUSE)
    def test_a_declared_currency_symbol_is_recognised(self):
        parser = picture.build_parser(currency_symbols="€")
        analysis = picture.analyse(parser.parse("€ZZ,ZZ9"))
        assert analysis.category == "numeric_edited"
        assert analysis.char_positions == 7

    @covers(CobolFeature.PIC_CLAUSE)
    def test_a_barred_currency_symbol_is_refused(self):
        # literal-7 "must not contain ... alphabetic characters A, B, C, D, E, G,
        # N, P, R, S, U, V, X, Z" (p. 129).
        with pytest.raises(ValueError, match="cannot be used as a currency symbol"):
            picture.build_parser(currency_symbols="Z")
