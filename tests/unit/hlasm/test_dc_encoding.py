# pyright: standard
"""DC operands encode to byte images or relocated-address slots; images z390 assembles are checked in tests/z390/test_dc_image_differential.py, the rest follow the HLASM Language Reference examples: CU'UNICODE' is X'0055004E00490043004F00440045'."""

from __future__ import annotations

import pytest

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.address import Address
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.base_displacement_address import BaseDisplacementAddress
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.per_copy_addresses_nominal import PerCopyAddressesNominal
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import encode_dc
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType

FIELD = RelocAddress(kind="RELOC", section="HELLO", offset=8)
NEXT = RelocAddress(kind="RELOC", section="HELLO", offset=12)


def _item(
    type_: str,
    value: str,
    length: int,
    explicit_length: bool = False,
    duplication: int = 1,
    extension: str = "",
    length_unit: LengthUnit = LengthUnit.BYTE,
) -> DcItem:
    return DcItem(
        type=type_,
        extension=extension,
        duplication=duplication,
        length=length,
        length_unit=length_unit,
        explicit_length=explicit_length,
        scale=0,
        exponent=0,
        offset=0,
        bit_offset=0,
        nominal=StringNominal(kind="STRING", value=value),
    )


def _address_item(
    type_: str,
    values: tuple[Address, ...],
    length: int,
    explicit_length: bool = False,
) -> DcItem:
    return DcItem(
        type=type_,
        extension="",
        duplication=1,
        length=length,
        length_unit=LengthUnit.BYTE,
        explicit_length=explicit_length,
        scale=0,
        exponent=0,
        offset=0,
        bit_offset=0,
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
        _item("F", "", 4, duplication=0).model_copy(
            update={"nominal": OmittedNominal(kind="OMITTED")}
        ),
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
        _address_item("A", (), 4).model_copy(
            update={
                "duplication": 2,
                "nominal": PerCopyAddressesNominal(
                    kind="ADDRESSES_PER_COPY", copies=((FIELD,), (NEXT,))
                ),
            }
        ),
    )
    assert [encode_dc(item) for item in items] == [
        (AddressSlot(FIELD, 4), ConstantImage((0, 0, 0, 8))),
        (ConstantImage((0xFF, 0xFF)),),
        (AddressSlot(FIELD, 3),),
        (AddressSlot(FIELD, 2),),
        (ConstantImage((0, 0, 0, 0)),),
        (AddressSlot(FIELD, 4), AddressSlot(NEXT, 4)),
    ]


def _based(base: int, displacement: int) -> BaseDisplacementAddress:
    return BaseDisplacementAddress(
        kind="BASE_DISPLACEMENT", base=base, displacement=displacement
    )


def test_doubleword_character_set_and_base_displacement_types():
    items = (
        _item("F", "-2", 8, extension="D"),
        _item("C", "AB", 2, extension="A"),
        _item("C", "AB", 5, explicit_length=True, extension="A"),
        _item("C", "A", 1, extension="E"),
        _item("C", "UNICODE", 14, extension="U"),
        _item("C", "A", 6, explicit_length=True, extension="U"),
        _address_item("A", (AbsAddress(kind="ABS", value=8),), 8).model_copy(
            update={"extension": "D"}
        ),
        _address_item("S", (_based(12, 8), _based(0, 100)), 2),
        _address_item("S", (_based(12, 8), _based(9, -2)), 3).model_copy(
            update={"extension": "Y"}
        ),
    )
    assert [_image(item) for item in items] == [
        [0xFF] * 7 + [0xFE],
        [0x41, 0x42],
        [0x41, 0x42, 0x20, 0x20, 0x20],
        [0xC1],
        list(bytes.fromhex("0055004E00490043004F00440045")),
        [0x00, 0x41, 0x00, 0x20, 0x00, 0x20],
        [0, 0, 0, 0, 0, 0, 0, 8],
        [0xC0, 0x08, 0x00, 0x64],
        [0xC0, 0x08, 0x00, 0x9F, 0xFE, 0xFF],
    ]
    assert encode_dc(
        _address_item("A", (FIELD,), 8).model_copy(update={"extension": "D"})
    ) == (
        AddressSlot(FIELD, 8),
    )
    assert encode_dc(
        _address_item(
            "V", (ExternalAddress(kind="EXTERNAL", name="EXTRN"),), 8
        ).model_copy(update={"extension": "D"})
    ) == (ConstantImage((0,) * 8),)


@pytest.mark.parametrize(
    ("type_", "extension", "message"),
    [
        ("E", "", "DC type E is not supported yet — red-dragon-6uyp.94"),
        ("D", "", "DC type D is not supported yet — red-dragon-6uyp.94"),
        ("L", "", "DC type L is not supported yet — red-dragon-6uyp.94"),
        ("E", "H", "DC type EH is not supported yet — red-dragon-6uyp.94"),
        ("Q", "", "DC type Q is not supported yet — red-dragon-6uyp.96"),
        ("J", "", "DC type J is not supported yet — red-dragon-6uyp.96"),
        ("G", "", "DC type G is not supported yet — red-dragon-6uyp.63"),
        ("R", "", "DC type R is not supported yet — red-dragon-6uyp.63"),
        ("X", "A", "DC type XA is not supported yet — red-dragon-6uyp.63"),
    ],
)
def test_rejects_types_without_an_encoding(type_: str, extension: str, message: str):
    with pytest.raises(UnsupportedDataType) as refused:
        encode_dc(_item(type_, "1", 4, extension=extension))
    assert str(refused.value) == message


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (
            _item("B", "1010", 4, True, length_unit=LengthUnit.BIT),
            "DC type BL.4 is not supported yet — red-dragon-6uyp.93",
        ),
        (
            _item("F", "1", 4).model_copy(update={"scale": 2}),
            "DC type F with a scale or exponent modifier is not supported yet — red-dragon-6uyp.93",
        ),
        (
            _item("H", "100", 2).model_copy(update={"exponent": 1}),
            "DC type H with a scale or exponent modifier is not supported yet — red-dragon-6uyp.93",
        ),
    ],
)
def test_refuses_what_waits_for_the_dc_encoder(item: DcItem, message: str):
    with pytest.raises(UnsupportedDataType) as refused:
        encode_dc(item)
    assert str(refused.value) == message
