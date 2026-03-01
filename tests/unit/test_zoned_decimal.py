"""Tests for zoned decimal encoding/decoding.

Test vectors ported from smojol DataTypesTest.java.
"""

from interpreter.cobol.zoned_decimal import encode_zoned, decode_zoned


class TestEncodeZoned:
    """Encoding tests from smojol DataTypesTest.java."""

    def test_unsigned_integer(self):
        """PIC 9(5) VALUE 12345."""
        result = encode_zoned("12345", 5, 0, signed=False)
        assert result == bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])

    def test_unsigned_with_decimal(self):
        """PIC 9(3)V9(2) VALUE 123.45."""
        result = encode_zoned("123.45", 5, 2, signed=False)
        assert result == bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])

    def test_signed_positive(self):
        """PIC S9(5) VALUE 12345 → last byte sign = 0xC."""
        result = encode_zoned("12345", 5, 0, signed=True)
        assert result == bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xC5])

    def test_signed_negative(self):
        """PIC S9(5) VALUE -12345 → last byte sign = 0xD."""
        result = encode_zoned("-12345", 5, 0, signed=True)
        assert result == bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xD5])

    def test_empty_string_gives_zeros(self):
        """PIC 9(3) VALUE '' → all zero digits."""
        result = encode_zoned("", 3, 0, signed=False)
        assert result == bytes([0xF0, 0xF0, 0xF0])

    def test_negative_zero_becomes_positive(self):
        """PIC S9(3) VALUE -0 → positive sign (no negative zero)."""
        result = encode_zoned("-0", 3, 0, signed=True)
        assert result == bytes([0xF0, 0xF0, 0xC0])

    def test_overflow_left_truncation(self):
        """PIC 9(3) VALUE 12345 → keeps rightmost 3 digits."""
        result = encode_zoned("12345", 3, 0, signed=False)
        assert result == bytes([0xF3, 0xF4, 0xF5])

    def test_short_value_zero_padded(self):
        """PIC 9(5) VALUE 42 → left-padded with zeros."""
        result = encode_zoned("42", 5, 0, signed=False)
        assert result == bytes([0xF0, 0xF0, 0xF0, 0xF4, 0xF2])

    def test_decimal_alignment(self):
        """PIC 9(2)V9(2) VALUE 2.3 → '0230'."""
        result = encode_zoned("2.3", 4, 2, signed=False)
        assert result == bytes([0xF0, 0xF2, 0xF3, 0xF0])

    def test_leading_decimal(self):
        """PIC 9(2)V9(2) VALUE .5678 → '0056'."""
        result = encode_zoned(".5678", 4, 2, signed=False)
        assert result == bytes([0xF0, 0xF0, 0xF5, 0xF6])

    def test_single_digit(self):
        """PIC 9(1) VALUE 7."""
        result = encode_zoned("7", 1, 0, signed=False)
        assert result == bytes([0xF7])

    def test_signed_single_digit_positive(self):
        """PIC S9(1) VALUE 7 → sign 0xC."""
        result = encode_zoned("7", 1, 0, signed=True)
        assert result == bytes([0xC7])

    def test_signed_single_digit_negative(self):
        """PIC S9(1) VALUE -7 → sign 0xD."""
        result = encode_zoned("-7", 1, 0, signed=True)
        assert result == bytes([0xD7])


class TestDecodeZoned:
    """Decoding tests."""

    def test_unsigned_integer(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])
        assert decode_zoned(data, 0) == 12345.0

    def test_with_decimal(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])
        assert decode_zoned(data, 2) == 123.45

    def test_signed_positive(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xC5])
        assert decode_zoned(data, 0) == 12345.0

    def test_signed_negative(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xD5])
        assert decode_zoned(data, 0) == -12345.0

    def test_empty_data(self):
        assert decode_zoned(b"", 0) == 0.0

    def test_all_zeros(self):
        data = bytes([0xF0, 0xF0, 0xF0])
        assert decode_zoned(data, 0) == 0.0


class TestZonedRoundTrip:
    """Round-trip encode → decode tests."""

    def test_round_trip_unsigned(self):
        encoded = encode_zoned("12345", 5, 0, signed=False)
        assert decode_zoned(encoded, 0) == 12345.0

    def test_round_trip_signed_positive(self):
        encoded = encode_zoned("678", 3, 0, signed=True)
        assert decode_zoned(encoded, 0) == 678.0

    def test_round_trip_signed_negative(self):
        encoded = encode_zoned("-42", 3, 0, signed=True)
        assert decode_zoned(encoded, 0) == -42.0

    def test_round_trip_with_decimal(self):
        encoded = encode_zoned("12.34", 4, 2, signed=False)
        assert decode_zoned(encoded, 2) == 12.34
