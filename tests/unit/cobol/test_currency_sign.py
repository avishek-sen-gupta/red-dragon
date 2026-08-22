"""CURRENCY SIGN IS — a program-scoped replacement for '$' in PICTURE strings.

Expected values come from NIST-85 NC107A.CBL, the conformance program dedicated
to the CURRENCY SIGN and DECIMAL-POINT clauses, vendored at
proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/. Its
SPECIAL-NAMES declares:

    CURRENCY SIGN IS "W"
    DECIMAL-POINT IS COMMA.

and it asserts `DATA-J PICTURE IS WWWWW` holding 12 equals '  W12' — i.e. the
configured symbol is a full participant in floating insertion, behaving exactly
as '$$$$$' would give '  $12'. It is not a special case bolted on beside '$'.

DECIMAL-POINT IS COMMA is deliberately out of scope here (red-dragon-3o5f was
split): it changes numeric LITERALS as well as pictures, so it has a far wider
blast radius. Only the currency half is implemented.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.edit_picture import (
    UnsupportedEditPictureError,
    format_edited,
    parse_edit_picture,
)
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.pic_parser import parse_pic
from tests.covers import covers


class TestCurrencySymbolFloats:
    """A configured currency symbol behaves exactly as '$' does."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_nist_floating_w_currency(self):
        """NIST NC107A: PIC WWWWW holding 12 is '  W12'."""
        assert format_edited("12", "WWWWW", currency="W") == "  W12"

    @covers(CobolFeature.NUMERIC_EDITED)
    @pytest.mark.parametrize(
        ("value", "pic", "expected"),
        [
            # The '$' cases from NIST NC124A, transliterated to 'W'. If the
            # symbol is genuinely a parameter these must match one-for-one.
            ("0", "WW,WWW.WW", "         "),
            (".02", "WW,WWW.WW", "     W.02"),
            ("12", "WW,WWW.WW", "   W12.00"),
            ("1234", "WW,WWW.WW", "W1,234.00"),
            ("0", "WWWWW.99", "    W.00"),
            ("12", "WW99", " W12"),
            ("1234", "WWWW9", "W1234"),
        ],
    )
    def test_mirrors_dollar_behaviour(self, value: str, pic: str, expected: str):
        assert format_edited(value, pic, currency="W") == expected

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_single_configured_symbol_is_fixed_insertion(self):
        """A run of ONE is fixed insertion for 'W' just as for '$'."""
        assert format_edited("1234.5", "WZZZ,ZZZ.99", currency="W") == "W  1,234.50"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_dollar_is_not_special_when_another_symbol_is_configured(self):
        """With CURRENCY SIGN IS 'W', a literal '$' in a picture is NOT a
        currency symbol — it is an ordinary character. Leaving '$' hardcoded
        alongside 'W' would silently give a picture two currency symbols."""
        ep = parse_edit_picture("WWWW.99", currency="W")
        assert ep.float_symbol == "W"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_default_currency_is_dollar(self):
        """A program with no CURRENCY SIGN clause keeps '$' — the parameter
        must default, or every existing caller changes behaviour."""
        assert format_edited("1234", "$$,$$$.99") == "$1,234.00"
        assert parse_edit_picture("$$$$.99").float_symbol == "$"


class TestCurrencyThreadingToParsePic:
    """The program-scoped symbol reaches parse_pic and the field descriptor."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_parse_pic_classifies_configured_currency_picture(self):
        """PIC WWWWW is numeric-edited ONLY if parse_pic knows 'W' is the
        currency symbol. Without it there are no digit positions at all and
        the picture falls through to the Lark grammar as a hard error."""
        d = parse_pic("WWWWW", currency="W")
        assert d.category == CobolDataCategory.NUMERIC_EDITED
        assert d.byte_length == 5

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_width_is_unchanged_by_symbol_substitution(self):
        """Single-character substitution is one symbol for one symbol, so the
        byte width must be identical to the '$' equivalent. This is the
        parity the bridge's uniform rule depends on (red-dragon-ilb6)."""
        assert (
            parse_pic("WW,WWW.99", currency="W").byte_length
            == parse_pic("$$,$$$.99").byte_length
        )

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_field_ingestion_carries_the_currency_symbol(self):
        fld = CobolField(
            name="WS-AMT",
            level=5,
            pic="WW,WWW.99",
            usage="DISPLAY",
            offset=0,
            currency_symbol="W",
        )
        assert fld.type_descriptor.category == CobolDataCategory.NUMERIC_EDITED
        assert fld.type_descriptor.byte_length == 9

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_field_defaults_to_dollar(self):
        fld = CobolField(
            name="WS-AMT", level=5, pic="$$,$$$.99", usage="DISPLAY", offset=0
        )
        assert fld.type_descriptor.byte_length == 9


class TestCurrencyFromTheAsgContract:
    """CobolASG.from_dict reads SPECIAL-NAMES off the bridge JSON and pushes
    the symbol down through the existing CobolField.from_dict recursion."""

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_currency_sign_reaches_nested_fields(self):
        asg = CobolASG.from_dict(
            {
                "program_id": "CURTEST",
                "special_names": {"currency_sign": "W"},
                "data_fields": [
                    {
                        "name": "WS-REC",
                        "level": 1,
                        "pic": "",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "children": [
                            {
                                "name": "WS-AMT",
                                "level": 5,
                                "pic": "WW,WWW.99",
                                "usage": "DISPLAY",
                                "offset": 0,
                            }
                        ],
                    }
                ],
            }
        )
        child = asg.data_fields[0].children[0]
        assert child.currency_symbol == "W"
        assert child.type_descriptor.category == CobolDataCategory.NUMERIC_EDITED

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_absent_special_names_defaults_to_dollar(self):
        asg = CobolASG.from_dict(
            {
                "program_id": "NOCUR",
                "data_fields": [
                    {
                        "name": "WS-AMT",
                        "level": 5,
                        "pic": "$$,$$$.99",
                        "usage": "DISPLAY",
                        "offset": 0,
                    }
                ],
            }
        )
        assert asg.data_fields[0].currency_symbol == "$"
        assert asg.data_fields[0].type_descriptor.byte_length == 9

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_multi_character_currency_is_refused(self):
        """CURRENCY SIGN IS 'EUR' WITH PICTURE SYMBOL '$' makes each symbol
        position occupy len(literal) bytes, which CHANGES the field width and
        would desynchronise the bridge's offsets from Python's read lengths.
        Out of scope — refuse loudly rather than silently mis-size."""
        with pytest.raises(UnsupportedEditPictureError, match="CURRENCY"):
            CobolASG.from_dict(
                {
                    "program_id": "MULTICUR",
                    "special_names": {
                        "currency_sign": "EUR",
                        "currency_picture_symbol": "$",
                    },
                    "data_fields": [],
                }
            )


class TestCurrencySurvivesAsgRoundTrip:
    """CobolASG.to_dict must emit special_names, or a round trip silently
    reverts the program to '$'.

    from_dict/to_dict asymmetry is invisible until something serialises an ASG
    and reads it back — at which point every edited field in the program
    formats with the wrong symbol, with nothing raising.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_round_trip_preserves_currency_symbol(self):
        original = CobolASG.from_dict(
            {
                "program_id": "CURTEST",
                "special_names": {"currency_sign": "W"},
                "data_fields": [
                    {
                        "name": "WS-AMT",
                        "level": 5,
                        "pic": "WW,WWW.99",
                        "usage": "DISPLAY",
                        "offset": 0,
                    }
                ],
            }
        )
        assert original.data_fields[0].currency_symbol == "W"

        revived = CobolASG.from_dict(original.to_dict())
        assert revived.data_fields[0].currency_symbol == "W"
        assert (
            revived.data_fields[0].type_descriptor.category
            == CobolDataCategory.NUMERIC_EDITED
        )

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_round_trip_without_clause_stays_dollar(self):
        original = CobolASG.from_dict(
            {
                "program_id": "NOCUR",
                "data_fields": [
                    {
                        "name": "WS-AMT",
                        "level": 5,
                        "pic": "$$,$$$.99",
                        "usage": "DISPLAY",
                        "offset": 0,
                    }
                ],
            }
        )
        revived = CobolASG.from_dict(original.to_dict())
        assert revived.data_fields[0].currency_symbol == "$"
        assert "special_names" not in original.to_dict()
