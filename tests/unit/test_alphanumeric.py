"""Tests for alphanumeric EBCDIC encoding/decoding.

Test vectors ported from smojol AlphanumericDataTypeSpec.java.
"""

from interpreter.cobol.alphanumeric import (
    decode_alphanumeric,
    encode_alphanumeric,
    encode_hex_literal,
    parse_hex_literal,
)
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

EBCDIC_SPACE = 0x40


class TestParseHexLiteral:
    @covers(CobolFeature.VALUE_CLAUSE)
    def test_single_byte(self):
        assert parse_hex_literal("X'7D'") == b"\x7d"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_multi_byte(self):
        assert parse_hex_literal("X'C1C2'") == b"\xc1\xc2"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_lowercase_prefix(self):
        assert parse_hex_literal("x'7d'") == b"\x7d"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_lowercase_digits(self):
        assert parse_hex_literal("X'7d'") == b"\x7d"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_plain_string_is_not_hex(self):
        assert parse_hex_literal("A") is None

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_quoted_alpha_is_not_hex(self):
        # An ordinary alphanumeric VALUE must not be treated as hex.
        assert parse_hex_literal("HELLO") is None

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_odd_digit_count_rejected(self):
        assert parse_hex_literal("X'7'") is None

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_non_hex_digits_rejected(self):
        assert parse_hex_literal("X'ZZ'") is None

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_empty_inner_rejected(self):
        assert parse_hex_literal("X''") is None


class TestEncodeHexLiteral:
    @covers(CobolFeature.VALUE_CLAUSE)
    def test_single_byte_exact(self):
        assert encode_hex_literal(b"\x7d", 1) == b"\x7d"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_under_length_space_padded(self):
        assert encode_hex_literal(b"\x7d", 3) == b"\x7d" + bytes(
            [EBCDIC_SPACE, EBCDIC_SPACE]
        )

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_over_length_truncated(self):
        assert encode_hex_literal(b"\xc1\xc2\xc3", 2) == b"\xc1\xc2"

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_normal_value_still_ebcdic_translated(self):
        # Regression guard: a normal alphanumeric VALUE 'A' → EBCDIC 0xC1.
        assert encode_alphanumeric("A", 1) == bytes([0xC1])


class TestEncodeAlphanumeric:
    def test_exact_length(self):
        result = encode_alphanumeric("HELLO", 5)
        expected = EbcdicTable.ascii_to_ebcdic(b"HELLO")
        assert result == expected

    def test_over_length_truncated(self):
        result = encode_alphanumeric("HELLO WORLD", 5)
        expected = EbcdicTable.ascii_to_ebcdic(b"HELLO")
        assert result == expected

    def test_under_length_padded(self):
        result = encode_alphanumeric("HI", 5)
        expected_hi = EbcdicTable.ascii_to_ebcdic(b"HI")
        assert result[:2] == expected_hi
        assert result[2:] == bytes([EBCDIC_SPACE] * 3)

    def test_empty_string(self):
        result = encode_alphanumeric("", 3)
        assert result == bytes([EBCDIC_SPACE] * 3)

    def test_single_char(self):
        result = encode_alphanumeric("A", 1)
        assert result == EbcdicTable.ascii_to_ebcdic(b"A")

    def test_digits(self):
        result = encode_alphanumeric("123", 3)
        expected = EbcdicTable.ascii_to_ebcdic(b"123")
        assert result == expected


class TestDecodeAlphanumeric:
    def test_decode_hello(self):
        ebcdic = EbcdicTable.ascii_to_ebcdic(b"HELLO")
        assert decode_alphanumeric(ebcdic) == "HELLO"

    def test_decode_with_trailing_spaces(self):
        ebcdic = EbcdicTable.ascii_to_ebcdic(b"HI") + bytes([EBCDIC_SPACE] * 3)
        assert decode_alphanumeric(ebcdic) == "HI   "

    def test_decode_empty(self):
        assert decode_alphanumeric(b"") == ""

    def test_decode_digits(self):
        ebcdic = EbcdicTable.ascii_to_ebcdic(b"20260301")
        assert decode_alphanumeric(ebcdic) == "20260301"


class TestAlphanumericRoundTrip:
    def test_round_trip_hello(self):
        encoded = encode_alphanumeric("HELLO", 5)
        assert decode_alphanumeric(encoded) == "HELLO"

    def test_round_trip_with_padding(self):
        encoded = encode_alphanumeric("HI", 5)
        assert decode_alphanumeric(encoded) == "HI   "

    def test_round_trip_digits(self):
        encoded = encode_alphanumeric("20260301", 8)
        assert decode_alphanumeric(encoded) == "20260301"
