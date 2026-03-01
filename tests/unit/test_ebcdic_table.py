"""Tests for EBCDIC ↔ ASCII bidirectional conversion tables."""

from interpreter.cobol.ebcdic_table import EbcdicTable


class TestEbcdicTable:
    """Round-trip and known-mapping tests for EBCDIC conversion."""

    def test_known_mapping_digit_zero(self):
        assert EbcdicTable.ascii_to_ebcdic(b"0") == bytes([0xF0])

    def test_known_mapping_digit_nine(self):
        assert EbcdicTable.ascii_to_ebcdic(b"9") == bytes([0xF9])

    def test_known_mapping_letter_a(self):
        assert EbcdicTable.ascii_to_ebcdic(b"A") == bytes([0xC1])

    def test_known_mapping_letter_z(self):
        assert EbcdicTable.ascii_to_ebcdic(b"Z") == bytes([0xE9])

    def test_known_mapping_space(self):
        assert EbcdicTable.ascii_to_ebcdic(b" ") == bytes([0x40])

    def test_known_mapping_lowercase_a(self):
        assert EbcdicTable.ascii_to_ebcdic(b"a") == bytes([0x81])

    def test_ebcdic_to_ascii_digit_zero(self):
        assert EbcdicTable.ebcdic_to_ascii(bytes([0xF0])) == b"0"

    def test_ebcdic_to_ascii_letter_a(self):
        assert EbcdicTable.ebcdic_to_ascii(bytes([0xC1])) == b"A"

    def test_ebcdic_to_ascii_space(self):
        assert EbcdicTable.ebcdic_to_ascii(bytes([0x40])) == b" "

    def test_round_trip_all_digits(self):
        digits = b"0123456789"
        assert (
            EbcdicTable.ebcdic_to_ascii(EbcdicTable.ascii_to_ebcdic(digits)) == digits
        )

    def test_round_trip_uppercase_letters(self):
        letters = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        assert (
            EbcdicTable.ebcdic_to_ascii(EbcdicTable.ascii_to_ebcdic(letters)) == letters
        )

    def test_round_trip_lowercase_letters(self):
        letters = b"abcdefghijklmnopqrstuvwxyz"
        assert (
            EbcdicTable.ebcdic_to_ascii(EbcdicTable.ascii_to_ebcdic(letters)) == letters
        )

    def test_round_trip_common_punctuation(self):
        punct = b".,;:!?()+-*/<>=@#$%&"
        assert EbcdicTable.ebcdic_to_ascii(EbcdicTable.ascii_to_ebcdic(punct)) == punct

    def test_multi_byte_string(self):
        data = b"HELLO WORLD 123"
        ebcdic = EbcdicTable.ascii_to_ebcdic(data)
        assert len(ebcdic) == len(data)
        assert EbcdicTable.ebcdic_to_ascii(ebcdic) == data

    def test_empty_bytes(self):
        assert EbcdicTable.ascii_to_ebcdic(b"") == b""
        assert EbcdicTable.ebcdic_to_ascii(b"") == b""

    def test_all_ebcdic_digits_are_contiguous(self):
        """EBCDIC digits 0-9 should be 0xF0-0xF9."""
        for digit in range(10):
            ascii_byte = ord(str(digit))
            ebcdic_bytes = EbcdicTable.ascii_to_ebcdic(bytes([ascii_byte]))
            assert ebcdic_bytes[0] == 0xF0 + digit
