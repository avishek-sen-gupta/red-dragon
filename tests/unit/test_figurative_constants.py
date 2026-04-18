"""Unit tests for COBOL figurative constant translation."""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.figurative_constants import translate_cobol_figurative
from tests.covers import NotLanguageFeature, covers


class TestFigurativeConstantTranslation:
    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_space_translates_to_space_char(self):
        assert translate_cobol_figurative("SPACE") == " "

    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_spaces_translates_to_space_char(self):
        assert translate_cobol_figurative("SPACES") == " "

    @covers(CobolFeature.FIGURATIVE_ZEROS)
    def test_zero_translates_to_zero_char(self):
        assert translate_cobol_figurative("ZERO") == "0"

    @covers(CobolFeature.FIGURATIVE_ZEROS)
    def test_zeros_translates_to_zero_char(self):
        assert translate_cobol_figurative("ZEROS") == "0"

    @covers(CobolFeature.FIGURATIVE_ZEROS)
    def test_zeroes_translates_to_zero_char(self):
        assert translate_cobol_figurative("ZEROES") == "0"

    @covers(CobolFeature.FIGURATIVE_QUOTES)
    def test_quote_translates_to_double_quote(self):
        assert translate_cobol_figurative("QUOTE") == '"'

    @covers(CobolFeature.FIGURATIVE_QUOTES)
    def test_quotes_translates_to_double_quote(self):
        assert translate_cobol_figurative("QUOTES") == '"'

    @covers(CobolFeature.FIGURATIVE_LOW_VALUES)
    def test_low_value_translates_to_null_byte(self):
        assert translate_cobol_figurative("LOW-VALUE") == "\x00"

    @covers(CobolFeature.FIGURATIVE_LOW_VALUES)
    def test_low_values_translates_to_null_byte(self):
        assert translate_cobol_figurative("LOW-VALUES") == "\x00"

    @covers(CobolFeature.FIGURATIVE_HIGH_VALUES)
    def test_high_value_translates_to_max_byte(self):
        assert translate_cobol_figurative("HIGH-VALUE") == "\xff"

    @covers(CobolFeature.FIGURATIVE_HIGH_VALUES)
    def test_high_values_translates_to_max_byte(self):
        assert translate_cobol_figurative("HIGH-VALUES") == "\xff"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_unknown_token_passes_through(self):
        """Non-figurative names are returned unchanged."""
        assert translate_cobol_figurative("WS-FIELD") == "WS-FIELD"
        assert translate_cobol_figurative("HELLO") == "HELLO"
        assert translate_cobol_figurative("42") == "42"
