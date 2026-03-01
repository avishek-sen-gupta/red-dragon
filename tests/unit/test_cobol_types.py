"""Tests for COBOL type descriptors."""

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
        try:
            td.total_digits = 10  # type: ignore
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass

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
