"""Tests for alphanumeric EBCDIC encoding/decoding.

Test vectors ported from smojol AlphanumericDataTypeSpec.java.
"""

from interpreter.cobol.alphanumeric import encode_alphanumeric, decode_alphanumeric
from interpreter.cobol.ebcdic_table import EbcdicTable

EBCDIC_SPACE = 0x40


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
