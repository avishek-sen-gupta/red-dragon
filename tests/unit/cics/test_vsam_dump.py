from __future__ import annotations

from interpreter.cics.vsam.dump import _decode_leaf
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.comp3 import encode_comp3
from interpreter.cobol.binary import encode_binary
from tests.covers import covers, NotLanguageFeature


def _fl(category, offset, byte_length, total_digits, decimal_digits=0, signed=False):
    return FieldLayout(
        name="F",
        type_descriptor=CobolTypeDescriptor(
            category=category,
            total_digits=total_digits,
            decimal_digits=decimal_digits,
            signed=signed,
        ),
        offset=offset,
        byte_length=byte_length,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_alphanumeric_trims_trailing_spaces():
    fl = _fl(CobolDataCategory.ALPHANUMERIC, 0, 5, 5)
    data = EbcdicTable.ascii_to_ebcdic(b"AB   ")
    assert _decode_leaf(fl, data) == "AB"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_zoned_integer_is_int():
    fl = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 3, 3, decimal_digits=0)
    assert _decode_leaf(fl, b"\xf0\xf1\xf2") == 12
    assert isinstance(_decode_leaf(fl, b"\xf0\xf1\xf2"), int)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_zoned_decimal_is_float():
    fl = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 4, 4, decimal_digits=2)
    assert _decode_leaf(fl, b"\xf1\xf2\xf3\xf4") == 12.34


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_comp3_decimal():
    data = encode_comp3("123.45", 5, 2, True)
    fl = _fl(CobolDataCategory.COMP3, 0, len(data), 5, decimal_digits=2, signed=True)
    assert _decode_leaf(fl, data) == 123.45


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_binary_integer_is_int():
    data = encode_binary("42", 4, 0, True)
    fl = _fl(CobolDataCategory.BINARY, 0, len(data), 4, decimal_digits=0, signed=True)
    assert _decode_leaf(fl, data) == 42
    assert isinstance(_decode_leaf(fl, data), int)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_comp1_comp2_unsupported():
    import pytest

    fl = _fl(CobolDataCategory.COMP1, 0, 4, 0)
    with pytest.raises(NotImplementedError):
        _decode_leaf(fl, b"\x00\x00\x00\x00")
