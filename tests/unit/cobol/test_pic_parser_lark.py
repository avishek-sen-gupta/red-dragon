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
