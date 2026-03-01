"""Tests for COMP-3 packed BCD encoding/decoding.

Test vectors ported from smojol DataTypesTest.java.
"""

from interpreter.cobol.comp3 import encode_comp3, decode_comp3


class TestEncodeComp3:
    """Encoding tests from smojol DataTypesTest.java."""

    def test_unsigned_integer(self):
        """PIC 9(5) COMP-3 VALUE 12345 → 3 bytes (5//2 + 1)."""
        result = encode_comp3("12345", 5, 0, signed=False)
        # Odd digits: 1,2,3,4,5 + sign 0xF → 12 34 5F
        assert result == bytes([0x12, 0x34, 0x5F])

    def test_signed_positive(self):
        """PIC S9(5) COMP-3 VALUE 12345 → sign 0xC."""
        result = encode_comp3("12345", 5, 0, signed=True)
        assert result == bytes([0x12, 0x34, 0x5C])

    def test_signed_negative(self):
        """PIC S9(5) COMP-3 VALUE -12345 → sign 0xD."""
        result = encode_comp3("-12345", 5, 0, signed=True)
        assert result == bytes([0x12, 0x34, 0x5D])

    def test_even_digits(self):
        """PIC 9(4) COMP-3 VALUE 1234 → 3 bytes (4//2 + 1)."""
        result = encode_comp3("1234", 4, 0, signed=False)
        # Even digits: prepend 0 → 0,1,2,3,4 + sign 0xF → 01 23 4F
        assert result == bytes([0x01, 0x23, 0x4F])

    def test_zero(self):
        """PIC 9(3) COMP-3 VALUE 0."""
        result = encode_comp3("0", 3, 0, signed=False)
        assert result == bytes([0x00, 0x0F])

    def test_with_decimal(self):
        """PIC 9(3)V9(2) COMP-3 VALUE 123.45."""
        result = encode_comp3("123.45", 5, 2, signed=False)
        assert result == bytes([0x12, 0x34, 0x5F])

    def test_negative_zero_becomes_positive(self):
        """PIC S9(3) COMP-3 VALUE -0 → positive sign."""
        result = encode_comp3("-0", 3, 0, signed=True)
        assert result == bytes([0x00, 0x0C])


class TestDecodeComp3:
    """Decoding tests."""

    def test_unsigned_integer(self):
        data = bytes([0x12, 0x34, 0x5F])
        assert decode_comp3(data, 0) == 12345.0

    def test_signed_positive(self):
        data = bytes([0x12, 0x34, 0x5C])
        assert decode_comp3(data, 0) == 12345.0

    def test_signed_negative(self):
        data = bytes([0x12, 0x34, 0x5D])
        assert decode_comp3(data, 0) == -12345.0

    def test_with_decimal(self):
        data = bytes([0x12, 0x34, 0x5F])
        assert decode_comp3(data, 2) == 123.45

    def test_empty_data(self):
        assert decode_comp3(b"", 0) == 0.0


class TestComp3RoundTrip:
    """Round-trip encode → decode tests."""

    def test_round_trip_unsigned(self):
        encoded = encode_comp3("12345", 5, 0, signed=False)
        assert decode_comp3(encoded, 0) == 12345.0

    def test_round_trip_signed_positive(self):
        encoded = encode_comp3("678", 3, 0, signed=True)
        assert decode_comp3(encoded, 0) == 678.0

    def test_round_trip_signed_negative(self):
        encoded = encode_comp3("-42", 3, 0, signed=True)
        assert decode_comp3(encoded, 0) == -42.0

    def test_round_trip_with_decimal(self):
        encoded = encode_comp3("12.34", 4, 2, signed=False)
        assert decode_comp3(encoded, 2) == 12.34

    def test_arithmetic_via_decode_add_encode(self):
        """Decode two values, add them, re-encode — from smojol test."""
        a = encode_comp3("100", 5, 0, signed=False)
        b = encode_comp3("200", 5, 0, signed=False)
        sum_val = decode_comp3(a, 0) + decode_comp3(b, 0)
        result = encode_comp3(str(int(sum_val)), 5, 0, signed=False)
        assert decode_comp3(result, 0) == 300.0
