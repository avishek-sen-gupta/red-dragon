"""Tests for COMP/BINARY big-endian two's complement encoding/decoding.

COMP/BINARY uses big-endian two's complement representation.
Byte sizes: <=4 digits -> 2 bytes, <=9 digits -> 4 bytes, <=18 digits -> 8 bytes.
"""

from interpreter.cobol.binary import encode_binary, decode_binary


class TestEncodeBinary:
    """Encoding tests for COMP/BINARY."""

    def test_unsigned_small_integer(self):
        """PIC 9(4) COMP VALUE 1234 -> 2 bytes big-endian."""
        result = encode_binary("1234", total_digits=4, decimal_digits=0, signed=False)
        assert result == (1234).to_bytes(2, "big", signed=False)

    def test_signed_positive(self):
        """PIC S9(4) COMP VALUE 1234 -> 2 bytes signed big-endian."""
        result = encode_binary("1234", total_digits=4, decimal_digits=0, signed=True)
        assert result == (1234).to_bytes(2, "big", signed=True)

    def test_signed_negative(self):
        """PIC S9(4) COMP VALUE -1234 -> 2 bytes signed big-endian."""
        result = encode_binary("-1234", total_digits=4, decimal_digits=0, signed=True)
        assert result == (-1234).to_bytes(2, "big", signed=True)

    def test_medium_integer(self):
        """PIC 9(7) COMP VALUE 1234567 -> 4 bytes."""
        result = encode_binary(
            "1234567", total_digits=7, decimal_digits=0, signed=False
        )
        assert result == (1234567).to_bytes(4, "big", signed=False)

    def test_large_integer(self):
        """PIC 9(15) COMP VALUE 123456789012345 -> 8 bytes."""
        result = encode_binary(
            "123456789012345", total_digits=15, decimal_digits=0, signed=False
        )
        assert result == (123456789012345).to_bytes(8, "big", signed=False)

    def test_zero(self):
        """PIC 9(4) COMP VALUE 0 -> 2 zero bytes."""
        result = encode_binary("0", total_digits=4, decimal_digits=0, signed=False)
        assert result == bytes(2)

    def test_with_decimal(self):
        """PIC 9(3)V9(2) COMP VALUE 123.45 -> stored as 12345 in 4 bytes (5 digits)."""
        result = encode_binary("123.45", total_digits=5, decimal_digits=2, signed=False)
        assert result == (12345).to_bytes(4, "big", signed=False)

    def test_negative_zero_becomes_positive(self):
        """PIC S9(4) COMP VALUE -0 -> zero."""
        result = encode_binary("-0", total_digits=4, decimal_digits=0, signed=True)
        assert result == bytes(2)

    def test_boundary_4_digits(self):
        """PIC 9(4) COMP -> 2 bytes (boundary case)."""
        result = encode_binary("9999", total_digits=4, decimal_digits=0, signed=False)
        assert len(result) == 2
        assert result == (9999).to_bytes(2, "big", signed=False)

    def test_boundary_5_digits(self):
        """PIC 9(5) COMP -> 4 bytes (crosses into medium)."""
        result = encode_binary("12345", total_digits=5, decimal_digits=0, signed=False)
        assert len(result) == 4
        assert result == (12345).to_bytes(4, "big", signed=False)

    def test_boundary_9_digits(self):
        """PIC 9(9) COMP -> 4 bytes (boundary case)."""
        result = encode_binary(
            "123456789", total_digits=9, decimal_digits=0, signed=False
        )
        assert len(result) == 4
        assert result == (123456789).to_bytes(4, "big", signed=False)

    def test_boundary_10_digits(self):
        """PIC 9(10) COMP -> 8 bytes (crosses into large)."""
        result = encode_binary(
            "1234567890", total_digits=10, decimal_digits=0, signed=False
        )
        assert len(result) == 8
        assert result == (1234567890).to_bytes(8, "big", signed=False)


class TestDecodeBinary:
    """Decoding tests for COMP/BINARY."""

    def test_unsigned_small(self):
        data = (1234).to_bytes(2, "big", signed=False)
        assert decode_binary(data, decimal_digits=0, signed=False) == 1234.0

    def test_signed_positive(self):
        data = (1234).to_bytes(2, "big", signed=True)
        assert decode_binary(data, decimal_digits=0, signed=True) == 1234.0

    def test_signed_negative(self):
        data = (-1234).to_bytes(2, "big", signed=True)
        assert decode_binary(data, decimal_digits=0, signed=True) == -1234.0

    def test_medium_integer(self):
        data = (1234567).to_bytes(4, "big", signed=False)
        assert decode_binary(data, decimal_digits=0, signed=False) == 1234567.0

    def test_large_integer(self):
        data = (123456789012345).to_bytes(8, "big", signed=False)
        assert decode_binary(data, decimal_digits=0, signed=False) == 123456789012345.0

    def test_with_decimal(self):
        data = (12345).to_bytes(2, "big", signed=False)
        assert decode_binary(data, decimal_digits=2, signed=False) == 123.45

    def test_zero(self):
        data = bytes(2)
        assert decode_binary(data, decimal_digits=0, signed=False) == 0.0

    def test_empty_data(self):
        assert decode_binary(b"", decimal_digits=0, signed=False) == 0.0


class TestBinaryRoundTrip:
    """Round-trip encode -> decode tests."""

    def test_round_trip_unsigned(self):
        encoded = encode_binary("12345", 5, 0, signed=False)
        assert decode_binary(encoded, 0, signed=False) == 12345.0

    def test_round_trip_signed_positive(self):
        encoded = encode_binary("678", 3, 0, signed=True)
        assert decode_binary(encoded, 0, signed=True) == 678.0

    def test_round_trip_signed_negative(self):
        encoded = encode_binary("-42", 3, 0, signed=True)
        assert decode_binary(encoded, 0, signed=True) == -42.0

    def test_round_trip_with_decimal(self):
        encoded = encode_binary("12.34", 4, 2, signed=False)
        assert decode_binary(encoded, 2, signed=False) == 12.34

    def test_arithmetic_via_decode_add_encode(self):
        """Decode two values, add them, re-encode."""
        a = encode_binary("100", 5, 0, signed=False)
        b = encode_binary("200", 5, 0, signed=False)
        sum_val = decode_binary(a, 0, signed=False) + decode_binary(b, 0, signed=False)
        result = encode_binary(str(int(sum_val)), 5, 0, signed=False)
        assert decode_binary(result, 0, signed=False) == 300.0
