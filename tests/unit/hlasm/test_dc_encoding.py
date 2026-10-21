# pyright: standard
"""DC operands encode to their byte images, or to slots for relocated addresses."""

from __future__ import annotations

import pytest

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import encode_dc
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType

FIELD = RelocAddress(kind="RELOC", section="HELLO", offset=8)


def _item(
    type_: str,
    value: str,
    length: int,
    explicit_length: bool = False,
    duplication: int = 1,
    extension: str = "",
) -> DcItem:
    return DcItem(
        type=type_,
        extension=extension,
        duplication=duplication,
        length=length,
        explicit_length=explicit_length,
        nominal=StringNominal(kind="STRING", value=value),
    )


def _address_item(
    type_: str,
    values: tuple[AbsAddress | RelocAddress | ExternalAddress, ...],
    length: int,
    explicit_length: bool = False,
) -> DcItem:
    return DcItem(
        type=type_,
        extension="",
        duplication=1,
        length=length,
        explicit_length=explicit_length,
        nominal=AddressesNominal(kind="ADDRESSES", values=values),
    )


def _image(item: DcItem) -> list[int]:
    return [
        byte
        for piece in encode_dc(item)
        if isinstance(piece, ConstantImage)
        for byte in piece.image
    ]


def test_encodes_character_hex_binary_fixed_packed_zoned():
    items = (
        _item("C", "AB", 2),
        _item("C", "A", 4, explicit_length=True),
        _item("C", "ABC", 2, explicit_length=True),
        _item("C", "A,B", 3),
        _item("X", "0A1", 2),
        _item("X", "0A1", 1, explicit_length=True),
        _item("X", "01,0203", 1),
        _item("B", "101", 1),
        _item("B", "1,100000000", 1),
        _item("F", "-1", 4),
        _item("F", "1,2", 4),
        _item("F", "300", 1, explicit_length=True),
        _item("F", "1", 4, duplication=2),
        _item("F", "1", 4, duplication=0),
        _item("H", "2", 2),
        _item("P", "-12", 3, explicit_length=True),
        _item("P", "1.5,-3", 2),
        _item("P", "123", 1, explicit_length=True),
        _item("Z", "12", 2),
        _item("Z", "-5", 3, explicit_length=True),
        _item("Z", "+1.2", 2),
    )
    assert [_image(item) for item in items] == [
        [0xC1, 0xC2],
        [0xC1, 0x40, 0x40, 0x40],
        [0xC1, 0xC2],
        [0xC1, 0x6B, 0xC2],
        [0x00, 0xA1],
        [0xA1],
        [0x01, 0x02, 0x03],
        [0x05],
        [0x01, 0x01, 0x00],
        [0xFF] * 4,
        [0, 0, 0, 1, 0, 0, 0, 2],
        [0x2C],
        [0, 0, 0, 1, 0, 0, 0, 1],
        [],
        [0, 2],
        [0x00, 0x01, 0x2D],
        [0x01, 0x5C, 0x3D],
        [0x3C],
        [0xF1, 0xC2],
        [0xF0, 0xF0, 0xD5],
        [0xF1, 0xC2],
    ]


def test_address_constants_are_absolute_relocated_or_external():
    items = (
        _address_item("A", (FIELD, AbsAddress(kind="ABS", value=8)), 4),
        _address_item("A", (AbsAddress(kind="ABS", value=-1),), 2, True),
        _address_item("A", (FIELD,), 3, explicit_length=True),
        _address_item("Y", (FIELD,), 2),
        _address_item("V", (ExternalAddress(kind="EXTERNAL", name="EXTRN"),), 4),
    )
    assert [encode_dc(item) for item in items] == [
        (AddressSlot(FIELD, 4), ConstantImage((0, 0, 0, 8))),
        (ConstantImage((0xFF, 0xFF)),),
        (AddressSlot(FIELD, 3),),
        (AddressSlot(FIELD, 2),),
        (ConstantImage((0, 0, 0, 0)),),
    ]


@pytest.mark.parametrize(
    ("type_", "extension", "message"),
    [
        ("E", "", "DC type E is not supported yet — red-dragon-6uyp.21"),
        ("D", "", "DC type D is not supported yet — red-dragon-6uyp.21"),
        ("L", "", "DC type L is not supported yet — red-dragon-6uyp.21"),
        ("E", "H", "DC type EH is not supported yet — red-dragon-6uyp.21"),
        ("C", "A", "DC type CA is not supported yet — red-dragon-6uyp.63"),
        ("S", "", "DC type S is not supported yet — red-dragon-6uyp.63"),
    ],
)
def test_rejects_types_without_an_encoding(type_: str, extension: str, message: str):
    with pytest.raises(UnsupportedDataType) as refused:
        encode_dc(_item(type_, "1", 4, extension=extension))
    assert str(refused.value) == message
