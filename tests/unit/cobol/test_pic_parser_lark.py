"""Tests for the Lark-based PIC parser rewrite (red-dragon-jznw).

These tests assert NEW structural-parse guarantees beyond the parity oracle
in tests/unit/test_pic_parser.py: the repeat count is read as a real integer
token (no regex/slice), CobolField computes its type_descriptor once at
ingestion, and sign-separate byte_length now includes the sign byte.
"""

from __future__ import annotations

import inspect

from interpreter.cobol import pic_parser
from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.pic_parser import parse_pic
from tests.covers import covers


class TestStructuralCount:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_repeat_count_is_structural(self):
        """parse_pic('9(12)') reads the count as an integer token -> 12 digits."""
        result = parse_pic("9(12)")
        assert result.total_digits == 12

    @covers(CobolFeature.PIC_CLAUSE)
    def test_no_regex_in_pic_parser(self):
        """The rewritten parser uses no regex: no `import re`, no re. usage."""
        source = inspect.getsource(pic_parser)
        assert "import re" not in source
        assert "_NUMBEROF_PATTERN" not in source


class TestCobolFieldTypeDescriptor:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_from_dict_computes_type_descriptor(self):
        """CobolField.from_dict computes a correct type_descriptor at ingestion."""
        field = CobolField.from_dict(
            {"name": "WS-AMT", "level": 5, "pic": "S9(5)V99", "usage": "DISPLAY"}
        )
        assert field.type_descriptor == CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=7,
            decimal_digits=2,
            signed=True,
        )


class TestSignSeparateByteLength:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_sign_separate_includes_sign_byte(self):
        """A sign-separate zoned field's byte_length includes the sign byte."""
        result = parse_pic("S9(5)", sign_separate=True)
        assert result.byte_length == 6


class TestNumericEditedPic:
    @covers(CobolFeature.NUMERIC_EDITED)
    def test_edited_pic_produces_numeric_edited_descriptor(self):
        """+99999999.99 -> NUMERIC_EDITED with width 12, decimal 2, signed."""
        result = parse_pic("+99999999.99")
        assert result.category == CobolDataCategory.NUMERIC_EDITED
        assert result.byte_length == 12
        assert result.decimal_digits == 2
        assert result.signed is True
        assert result.pic_string == "+99999999.99"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_edited_pic_with_suppression_and_commas(self):
        """+ZZZ,ZZZ,ZZZ.99 -> width 15 (commas/sign/decimal count as positions)."""
        result = parse_pic("+ZZZ,ZZZ,ZZZ.99")
        assert result.category == CobolDataCategory.NUMERIC_EDITED
        assert result.byte_length == 15

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_plain_numeric_is_not_edited(self):
        """A plain numeric PIC stays ZONED_DECIMAL, not NUMERIC_EDITED."""
        result = parse_pic("S9(5)V99")
        assert result.category == CobolDataCategory.ZONED_DECIMAL


class TestScalingOnlyPic:
    """Bare 'P' scaling pictures (no stored digit positions). NIST IX110A has
    ``01 STATUS-TEST-10 PIC P VALUE ZERO.`` — see red-dragon-m0oa.2."""

    @covers(CobolFeature.PIC_CLAUSE)
    def test_bare_p_parses_as_zero_digit_numeric(self):
        result = parse_pic("P")
        assert result.category == CobolDataCategory.ZONED_DECIMAL
        assert result.total_digits == 0
        assert result.decimal_digits == 0
        assert result.signed is False

    @covers(CobolFeature.PIC_CLAUSE)
    def test_multiple_p_parses(self):
        result = parse_pic("PPP")
        assert result.category == CobolDataCategory.ZONED_DECIMAL
        assert result.total_digits == 0

    @covers(CobolFeature.PIC_CLAUSE)
    def test_signed_scaling_only(self):
        result = parse_pic("SPP")
        assert result.signed is True
        assert result.total_digits == 0

    @covers(CobolFeature.PIC_CLAUSE)
    def test_leading_scaling_with_digit_still_parses(self):
        """PPP9 already parsed (scaling* before body); guard against regression."""
        result = parse_pic("PPP9")
        assert result.total_digits == 1

    @covers(CobolFeature.PIC_CLAUSE)
    def test_trailing_scaling_with_digit_still_parses(self):
        """9PPP already parsed (scaling* after body); guard against regression."""
        result = parse_pic("9PPP")
        assert result.total_digits == 1
