"""Tests for COBOL type descriptors."""

import pytest

from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor


class TestCobolTypeDescriptor:
    def test_zoned_decimal_byte_length(self):
        """Zoned decimal: 1 byte per digit."""
        td = CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL, total_digits=5
        )
        assert td.byte_length == 5

    def test_comp3_byte_length_odd_digits(self):
        """COMP-3 with 5 digits: (5 // 2) + 1 = 3 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.COMP3, total_digits=5)
        assert td.byte_length == 3

    def test_comp3_byte_length_even_digits(self):
        """COMP-3 with 4 digits: (4 // 2) + 1 = 3 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.COMP3, total_digits=4)
        assert td.byte_length == 3

    def test_alphanumeric_byte_length(self):
        """Alphanumeric: 1 byte per character."""
        td = CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=10
        )
        assert td.byte_length == 10

    def test_frozen_dataclass(self):
        """Type descriptors should be immutable."""
        td = CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL, total_digits=5
        )
        with pytest.raises(AttributeError):
            td.total_digits = 10  # type: ignore

    def test_with_decimal_digits(self):
        td = CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=7,
            decimal_digits=2,
            signed=True,
        )
        assert td.byte_length == 7
        assert td.decimal_digits == 2
        assert td.signed is True

    def test_binary_byte_length_small(self):
        """BINARY with 1-4 digits: 2 bytes (halfword)."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=4)
        assert td.byte_length == 2

    def test_binary_byte_length_medium(self):
        """BINARY with 5-9 digits: 4 bytes (fullword)."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=7)
        assert td.byte_length == 4

    def test_binary_byte_length_large(self):
        """BINARY with 10-18 digits: 8 bytes (doubleword)."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=15)
        assert td.byte_length == 8

    def test_binary_byte_length_boundary_4(self):
        """BINARY with exactly 4 digits: still 2 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=4)
        assert td.byte_length == 2

    def test_binary_byte_length_boundary_5(self):
        """BINARY with exactly 5 digits: crosses to 4 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=5)
        assert td.byte_length == 4

    def test_binary_byte_length_boundary_9(self):
        """BINARY with exactly 9 digits: still 4 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=9)
        assert td.byte_length == 4

    def test_binary_byte_length_boundary_10(self):
        """BINARY with exactly 10 digits: crosses to 8 bytes."""
        td = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=10)
        assert td.byte_length == 8

    def test_comp1_byte_length(self):
        """COMP-1: always 4 bytes (single-precision float)."""
        td = CobolTypeDescriptor(category=CobolDataCategory.COMP1, total_digits=0)
        assert td.byte_length == 4

    def test_comp2_byte_length(self):
        """COMP-2: always 8 bytes (double-precision float)."""
        td = CobolTypeDescriptor(category=CobolDataCategory.COMP2, total_digits=0)
        assert td.byte_length == 8
