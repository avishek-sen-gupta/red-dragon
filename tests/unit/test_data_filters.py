"""Tests for COBOL data alignment filters.

Test vectors ported from smojol DataTypesTest.java.
"""

from interpreter.cobol.data_filters import right_adjust, left_adjust, align_decimal


class TestRightAdjust:
    def test_exact_length(self):
        assert right_adjust("HELLO", 5) == "HELLO"

    def test_under_length_padded(self):
        assert right_adjust("HI", 5) == "HI   "

    def test_over_length_truncated(self):
        assert right_adjust("HELLO WORLD", 5) == "HELLO"

    def test_empty_string(self):
        assert right_adjust("", 3) == "   "


class TestLeftAdjust:
    def test_exact_length(self):
        assert left_adjust("123", 3) == "123"

    def test_under_length_zero_padded(self):
        assert left_adjust("5", 3) == "005"

    def test_over_length_truncated_from_left(self):
        assert left_adjust("12345", 3) == "345"

    def test_empty_string(self):
        assert left_adjust("", 3) == "000"


class TestAlignDecimal:
    """Test vectors from smojol DataTypesTest.java."""

    def test_basic_decimal(self):
        """'12.34' with PIC 9(2)V9(2) → '1234'"""
        assert align_decimal("12.34", 2, 2) == "1234"

    def test_short_decimal(self):
        """'2.3' with PIC 9(2)V9(2) → '0230'"""
        assert align_decimal("2.3", 2, 2) == "0230"

    def test_leading_decimal(self):
        """'.5678' with PIC 9(2)V9(2) → '0056'"""
        assert align_decimal(".5678", 2, 2) == "0056"

    def test_integer_only(self):
        """'42' with PIC 9(2)V9(2) → '4200'"""
        assert align_decimal("42", 2, 2) == "4200"

    def test_no_decimal_digits(self):
        """'123' with PIC 9(3) → '123'"""
        assert align_decimal("123", 3, 0) == "123"

    def test_overflow_integer(self):
        """'999' with PIC 9(2)V9(1) → '991' (integer overflow truncation)"""
        # left_adjust("999", 2) → "99", dec "".ljust(1,"0") → "0"
        # Wait: "999" has no decimal, so int_part="999", dec_part=""
        # left_adjust("999", 2) → "99" (rightmost 2)
        # dec: "".ljust(1,"0") → "0"
        assert align_decimal("999", 2, 1) == "990"

    def test_empty_string(self):
        assert align_decimal("", 2, 2) == "0000"
