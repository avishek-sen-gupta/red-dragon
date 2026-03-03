"""Tests for COBOL PIC clause parser."""

from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.pic_parser import parse_pic


class TestParsePicZonedDecimal:
    def test_simple_integer(self):
        result = parse_pic("9(5)")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=5,
            decimal_digits=0,
            signed=False,
        )

    def test_signed_with_decimal(self):
        result = parse_pic("S9(5)V99")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=7,
            decimal_digits=2,
            signed=True,
        )

    def test_signed_bare_digits(self):
        result = parse_pic("S99V99")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=4,
            decimal_digits=2,
            signed=True,
        )

    def test_only_fractional(self):
        result = parse_pic("V99")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=2,
            decimal_digits=2,
            signed=False,
        )

    def test_integer_with_decimal_point_no_fraction(self):
        result = parse_pic("9(5)V")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=5,
            decimal_digits=0,
            signed=False,
        )

    def test_bare_nine(self):
        result = parse_pic("9")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=1,
            decimal_digits=0,
            signed=False,
        )

    def test_multiple_nines(self):
        result = parse_pic("999")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=3,
            decimal_digits=0,
            signed=False,
        )

    def test_mixed_repeat_and_bare(self):
        result = parse_pic("9(3)V9(2)")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=5,
            decimal_digits=2,
            signed=False,
        )


class TestParsePicAlphanumeric:
    def test_simple_alphanumeric(self):
        result = parse_pic("X(8)")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=8,
            decimal_digits=0,
            signed=False,
        )

    def test_bare_x(self):
        result = parse_pic("X")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=1,
            decimal_digits=0,
            signed=False,
        )

    def test_mixed_alpha_and_digits(self):
        """Alphanumeric with digit indicators on the side -> still alphanumeric."""
        result = parse_pic("99X(3)")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=5,
            decimal_digits=0,
            signed=False,
        )

    def test_multiple_bare_x(self):
        result = parse_pic("XXX")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=3,
            decimal_digits=0,
            signed=False,
        )


class TestParsePicUsageOverride:
    def test_comp3_usage(self):
        result = parse_pic("S9(5)V99", usage="COMP-3")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.COMP3,
            total_digits=7,
            decimal_digits=2,
            signed=True,
        )

    def test_packed_decimal_usage(self):
        result = parse_pic("9(5)", usage="PACKED-DECIMAL")
        assert result == CobolTypeDescriptor(
            category=CobolDataCategory.COMP3,
            total_digits=5,
            decimal_digits=0,
            signed=False,
        )

    def test_display_usage_default(self):
        result = parse_pic("9(5)", usage="DISPLAY")
        assert result.category == CobolDataCategory.ZONED_DECIMAL

    def test_alphanumeric_ignores_usage_override(self):
        """USAGE override doesn't affect alphanumeric category."""
        result = parse_pic("X(10)", usage="COMP-3")
        assert result.category == CobolDataCategory.ALPHANUMERIC

    def test_comp_usage(self):
        result = parse_pic("S9(5)", usage="COMP")
        assert result.category == CobolDataCategory.BINARY
        assert result.total_digits == 5
        assert result.byte_length == 4

    def test_comp4_usage(self):
        result = parse_pic("9(4)", usage="COMP-4")
        assert result.category == CobolDataCategory.BINARY
        assert result.byte_length == 2

    def test_binary_usage(self):
        result = parse_pic("9(9)", usage="BINARY")
        assert result.category == CobolDataCategory.BINARY
        assert result.byte_length == 4

    def test_comp5_usage(self):
        result = parse_pic("9(5)", usage="COMP-5")
        assert result.category == CobolDataCategory.BINARY
        assert result.byte_length == 4

    def test_comp1_usage(self):
        """COMP-1 has no PIC clause — use empty PIC."""
        result = parse_pic("", usage="COMP-1")
        assert result.category == CobolDataCategory.COMP1
        assert result.byte_length == 4

    def test_comp2_usage(self):
        """COMP-2 has no PIC clause — use empty PIC."""
        result = parse_pic("", usage="COMP-2")
        assert result.category == CobolDataCategory.COMP2
        assert result.byte_length == 8


class TestParsePicBlankWhenZero:
    def test_blank_when_zero_propagated(self):
        """BLANK WHEN ZERO flag is propagated to the type descriptor."""
        result = parse_pic("9(5)", blank_when_zero=True)
        assert result.blank_when_zero is True
        assert result.category == CobolDataCategory.ZONED_DECIMAL

    def test_blank_when_zero_false_by_default(self):
        result = parse_pic("9(5)")
        assert result.blank_when_zero is False

    def test_blank_when_zero_not_on_alphanumeric(self):
        """BLANK WHEN ZERO on alphanumeric is ignored (not propagated)."""
        result = parse_pic("X(10)", blank_when_zero=True)
        assert result.blank_when_zero is False  # alphanumeric path doesn't set it
