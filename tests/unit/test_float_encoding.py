"""Tests for COMP-1 (single float) and COMP-2 (double float) encoding/decoding.

COMP-1: IEEE 754 single-precision, 4 bytes, big-endian.
COMP-2: IEEE 754 double-precision, 8 bytes, big-endian.
"""

import struct
import math

from interpreter.cobol.float_encoding import (
    encode_comp1,
    decode_comp1,
    encode_comp2,
    decode_comp2,
)


class TestEncodeComp1:
    """COMP-1 encoding tests (single-precision float, 4 bytes)."""

    def test_positive_integer(self):
        result = encode_comp1("100.0")
        assert result == struct.pack(">f", 100.0)

    def test_negative_value(self):
        result = encode_comp1("-3.14")
        assert result == struct.pack(">f", -3.14)

    def test_zero(self):
        result = encode_comp1("0")
        assert result == struct.pack(">f", 0.0)

    def test_small_fraction(self):
        result = encode_comp1("0.5")
        assert result == struct.pack(">f", 0.5)

    def test_always_4_bytes(self):
        result = encode_comp1("1.0")
        assert len(result) == 4


class TestDecodeComp1:
    """COMP-1 decoding tests."""

    def test_positive_integer(self):
        data = struct.pack(">f", 100.0)
        assert decode_comp1(data) == 100.0

    def test_negative_value(self):
        data = struct.pack(">f", -3.14)
        result = decode_comp1(data)
        assert abs(result - (-3.14)) < 1e-5

    def test_zero(self):
        data = struct.pack(">f", 0.0)
        assert decode_comp1(data) == 0.0

    def test_empty_data(self):
        assert decode_comp1(b"") == 0.0


class TestComp1RoundTrip:
    """Round-trip encode -> decode for COMP-1."""

    def test_round_trip_integer(self):
        encoded = encode_comp1("42.0")
        assert decode_comp1(encoded) == 42.0

    def test_round_trip_fraction(self):
        encoded = encode_comp1("0.25")
        assert decode_comp1(encoded) == 0.25

    def test_round_trip_negative(self):
        encoded = encode_comp1("-1.5")
        assert decode_comp1(encoded) == -1.5


class TestEncodeComp2:
    """COMP-2 encoding tests (double-precision float, 8 bytes)."""

    def test_positive_integer(self):
        result = encode_comp2("100.0")
        assert result == struct.pack(">d", 100.0)

    def test_negative_value(self):
        result = encode_comp2("-3.14159265358979")
        expected = struct.pack(">d", -3.14159265358979)
        assert result == expected

    def test_zero(self):
        result = encode_comp2("0")
        assert result == struct.pack(">d", 0.0)

    def test_large_value(self):
        result = encode_comp2("1e100")
        assert result == struct.pack(">d", 1e100)

    def test_always_8_bytes(self):
        result = encode_comp2("1.0")
        assert len(result) == 8


class TestDecodeComp2:
    """COMP-2 decoding tests."""

    def test_positive_integer(self):
        data = struct.pack(">d", 100.0)
        assert decode_comp2(data) == 100.0

    def test_negative_value(self):
        data = struct.pack(">d", -3.14159265358979)
        result = decode_comp2(data)
        assert abs(result - (-3.14159265358979)) < 1e-10

    def test_zero(self):
        data = struct.pack(">d", 0.0)
        assert decode_comp2(data) == 0.0

    def test_empty_data(self):
        assert decode_comp2(b"") == 0.0


class TestComp2RoundTrip:
    """Round-trip encode -> decode for COMP-2."""

    def test_round_trip_integer(self):
        encoded = encode_comp2("42.0")
        assert decode_comp2(encoded) == 42.0

    def test_round_trip_high_precision(self):
        encoded = encode_comp2("3.14159265358979")
        result = decode_comp2(encoded)
        assert abs(result - 3.14159265358979) < 1e-10

    def test_round_trip_negative(self):
        encoded = encode_comp2("-1.5")
        assert decode_comp2(encoded) == -1.5

    def test_round_trip_large_value(self):
        encoded = encode_comp2("1e50")
        assert decode_comp2(encoded) == 1e50
