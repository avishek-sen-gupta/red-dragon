from __future__ import annotations

import pytest

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
    assert isinstance(_decode_leaf(fl, b"\xf1\xf2\xf3\xf4"), float)


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
    fl = _fl(CobolDataCategory.COMP1, 0, 4, 0)
    with pytest.raises(NotImplementedError):
        _decode_leaf(fl, b"\x00\x00\x00\x00")


from interpreter.cics.vsam.dump import decode_record
from interpreter.cobol.data_layout import DataLayout


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_flat_fields():
    layout = DataLayout(
        fields={
            "ACCT-ID": _fl(CobolDataCategory.ALPHANUMERIC, 0, 11, 11),
            "ACCT-ACTIVE-STATUS": _fl(CobolDataCategory.ALPHANUMERIC, 11, 1, 1),
        },
        total_bytes=12,
    )
    record = EbcdicTable.ascii_to_ebcdic(b"00000000011") + EbcdicTable.ascii_to_ebcdic(
        b"N"
    )
    assert decode_record(layout, record) == {
        "ACCT-ID": "00000000011",
        "ACCT-ACTIVE-STATUS": "N",
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_nested_group():
    inner = DataLayout(
        fields={
            "FIRST": _fl(CobolDataCategory.ALPHANUMERIC, 0, 3, 3),
            "LAST": _fl(CobolDataCategory.ALPHANUMERIC, 3, 3, 3),
        },
        offset=0,
        total_bytes=6,
    )
    layout = DataLayout(groups={"NAME": inner}, total_bytes=6)
    record = EbcdicTable.ascii_to_ebcdic(b"BOBKAY")
    assert decode_record(layout, record) == {"NAME": {"FIRST": "BOB", "LAST": "KAY"}}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_redefines_both_views():
    # Two fields over the same 4 bytes: text view + a group view.
    base = _fl(CobolDataCategory.ALPHANUMERIC, 0, 4, 4)
    redef = FieldLayout(
        name="AS-NUM",
        type_descriptor=base.type_descriptor.__class__(
            category=CobolDataCategory.ZONED_DECIMAL, total_digits=4
        ),
        offset=0,
        byte_length=4,
        redefines="AS-TEXT",
    )
    layout = DataLayout(fields={"AS-TEXT": base, "AS-NUM": redef}, total_bytes=4)
    record = b"\xf1\xf2\xf3\xf4"
    out = decode_record(layout, record)
    assert out["AS-NUM"] == 1234  # zoned int view
    assert "AS-TEXT" in out  # both views present


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_rebases_subgroup_offset():
    # A sub-01 selected from a multi-01 copybook sits at a non-zero absolute offset;
    # decode_record must rebase so slicing is relative to the record start.
    inner = DataLayout(
        fields={"X": _fl(CobolDataCategory.ALPHANUMERIC, 20, 2, 2)},
        offset=20,
        total_bytes=2,
    )
    record = EbcdicTable.ascii_to_ebcdic(b"HI")
    assert decode_record(inner, record) == {"X": "HI"}
