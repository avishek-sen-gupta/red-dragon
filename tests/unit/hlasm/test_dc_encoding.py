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
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.per_copy_addresses_nominal import PerCopyAddressesNominal
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.bit_length_image import BitLengthImage
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import encode_dc
from interpreter.hlasm.dc_exponent_out_of_range import DcExponentOutOfRange
from interpreter.hlasm.dc_value_out_of_range import DcValueOutOfRange
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType

ORIGIN = MacroOrigin(kind="MACRO", file="src/t.asm", line=7, macro="GEN", depth=1)
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
    pieces = encode_dc(item, ORIGIN)
    assert not isinstance(pieces, BitLengthImage)
    return [
        byte
        for piece in pieces
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
        _item("F", "-1", 1, explicit_length=True),
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
        [0xFF],
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
    assert [encode_dc(item, ORIGIN) for item in items] == [
        (AddressSlot(FIELD, 4), ConstantImage((0, 0, 0, 8))),
        (ConstantImage((0xFF, 0xFF)),),
        (AddressSlot(FIELD, 3),),
        (AddressSlot(FIELD, 2),),
        (ConstantImage((0, 0, 0, 0)),),
        (AddressSlot(FIELD, 4), AddressSlot(NEXT, 4)),
    ]


def _fixed(value: str, length: int, scale: int = 0, exponent: int = 0) -> DcItem:
    return _item("F", value, length, explicit_length=length != 4).model_copy(
        update={"scale": scale, "exponent": exponent}
    )


def test_fixed_point_nominals_round_scale_and_take_exponents():
    items = (
        _fixed("1.5", 4),
        _fixed("-1.5", 4),
        _fixed("1.4", 4),
        _fixed("2.5", 4),
        _fixed(".5", 4),
        _fixed("1E-1", 4),
        _fixed("0.25", 4, scale=1),
        _fixed("3", 4, scale=-1),
        _fixed("1", 4, scale=2),
        _fixed("1.25", 4, scale=4),
        _fixed("15", 4, exponent=-1),
        _fixed("100", 4, exponent=1),
        _fixed("1.5", 4, exponent=1),
        _fixed("1E2", 4),
        _fixed("1.5E1", 4),
        _fixed("123 456", 4),
        _fixed("U4294967295", 4),
        _fixed("-2147483648", 4),
        _fixed("U255", 1),
        _fixed("-128", 1),
        _item("H", "-3.5", 2).model_copy(update={"scale": 1}),
        _item("H", "-1E2", 2),
        _item("H", "U65535", 2),
        _item("H", "-25.46", 2).model_copy(update={"scale": 6}),
        _item("F", "U18446744073709551615", 8, extension="D"),
        _item("F", "-9223372036854775808", 8, extension="D"),
    )
    assert [_image(item) for item in items] == [
        [0, 0, 0, 2],
        [0xFF, 0xFF, 0xFF, 0xFE],
        [0, 0, 0, 1],
        [0, 0, 0, 3],
        [0, 0, 0, 1],
        [0, 0, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 0, 2],
        [0, 0, 0, 4],
        [0, 0, 0, 0x14],
        [0, 0, 0, 2],
        [0, 0, 0x03, 0xE8],
        [0, 0, 0, 0x0F],
        [0, 0, 0, 0x64],
        [0, 0, 0, 0x0F],
        [0, 0x01, 0xE2, 0x40],
        [0xFF] * 4,
        [0x80, 0, 0, 0],
        [0xFF],
        [0x80],
        [0xFF, 0xF9],
        [0xFF, 0x9C],
        [0xFF, 0xFF],
        [0xF9, 0xA3],
        [0xFF] * 8,
        [0x80] + [0] * 7,
    ]


@pytest.mark.parametrize(
    ("item", "constant"),
    [
        (_fixed("2147483648", 4), "F'2147483648'"),
        (_fixed("-2147483649", 4), "F'-2147483649'"),
        (_fixed("U4294967296", 4), "F'U4294967296'"),
        (_fixed("128", 1), "F'128'"),
        (_fixed("1E10", 4), "F'1E10'"),
        (_fixed("1", 4, scale=31), "F'1'"),
        (_fixed("2147483647.5", 4), "F'2147483647.5'"),
        (_item("H", "32768", 2), "H'32768'"),
        (_item("H", "1,U65536", 2), "H'U65536'"),
        (
            _item("F", "9223372036854775808", 8, extension="D"),
            "FD'9223372036854775808'",
        ),
    ],
)
def test_fixed_point_values_outside_their_length_refuse(item: DcItem, constant: str):
    with pytest.raises(DcValueOutOfRange) as refused:
        encode_dc(item, ORIGIN)
    assert str(refused.value) == (
        f"{constant} at line 7 of src/t.asm does not fit its length — ASMA072E"
    )


def _absolute_y(value: int) -> DcItem:
    return _address_item("Y", (AbsAddress(kind="ABS", value=value),), 2)


def test_y_constants_hold_a_signed_or_unsigned_halfword_and_refuse_beyond_it():
    assert [_image(_absolute_y(value)) for value in (65535, -32768)] == [
        [0xFF, 0xFF],
        [0x80, 0x00],
    ]
    for value in (70000, -32769):
        with pytest.raises(DcValueOutOfRange) as refused:
            encode_dc(_absolute_y(value), ORIGIN)
        assert str(refused.value) == (
            f"Y({value}) at line 7 of src/t.asm does not fit its length — ASMA072E"
        )


@pytest.mark.parametrize(
    ("item", "constant"),
    [
        (_fixed("1E-90", 4), "F'1E-90'"),
        (_fixed("1E76", 4), "F'1E76'"),
        (_fixed("1E9999999", 4), "F'1E9999999'"),
        (_fixed("1E-9999999", 4), "F'1E-9999999'"),
        (_fixed("1E70", 4, exponent=10), "F'1E70'"),
    ],
)
def test_a_written_exponent_outside_its_range_refuses(item: DcItem, constant: str):
    with pytest.raises(DcExponentOutOfRange) as refused:
        encode_dc(item, ORIGIN)
    assert str(refused.value) == (
        f"{constant} at line 7 of src/t.asm has an exponent outside -85 to +75"
    )


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
        _address_item("A", (FIELD,), 8).model_copy(update={"extension": "D"}), ORIGIN
    ) == (
        AddressSlot(FIELD, 8),
    )
    assert encode_dc(
        _address_item(
            "V", (ExternalAddress(kind="EXTERNAL", name="EXTRN"),), 8
        ).model_copy(update={"extension": "D"}),
        ORIGIN,
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
        encode_dc(_item(type_, "1", 4, extension=extension), ORIGIN)
    assert str(refused.value) == message


def _bit_item(type_: str, value: str, bits: int, duplication: int = 1) -> DcItem:
    return _item(type_, value, bits, True, duplication, length_unit=LengthUnit.BIT)


def test_bit_length_operands_encode_each_value_in_its_bits():
    items = (
        _bit_item("F", "-1,1000", 12),
        _bit_item("F", "-2", 12, duplication=3),
        _bit_item("B", "1,0,1", 3),
        _bit_item("X", "ABCDE", 12),
        _bit_item("C", "AB", 12),
        _bit_item("C", "A", 12),
        _item("C", "A", 12, True, extension="A", length_unit=LengthUnit.BIT),
        _bit_item("P", "5", 12),
        _bit_item("Z", "5", 12),
        _bit_item("H", "3", 4),
        _address_item("A", (AbsAddress(kind="ABS", value=-1),), 4).model_copy(
            update={"length_unit": LengthUnit.BIT, "explicit_length": True}
        ),
    )
    assert [encode_dc(item, ORIGIN) for item in items] == [
        BitLengthImage((0xFFF, 0x3E8), 12),
        BitLengthImage((0xFFE,) * 3, 12),
        BitLengthImage((1, 0, 1), 3),
        BitLengthImage((0xCDE,), 12),
        BitLengthImage((0xC1C,), 12),
        BitLengthImage((0xC14,), 12),
        BitLengthImage((0x412,), 12),
        BitLengthImage((0x05C,), 12),
        BitLengthImage((0x0C5,), 12),
        BitLengthImage((3,), 4),
        BitLengthImage((0xF,), 4),
    ]


def test_bit_length_fixed_point_outside_its_bits_refuses():
    with pytest.raises(DcValueOutOfRange) as refused:
        encode_dc(_bit_item("F", "4000", 12), ORIGIN)
    assert str(refused.value) == (
        "F'4000' at line 7 of src/t.asm does not fit its length — ASMA072E"
    )


def test_location_counter_in_bit_length_copies_refuses():
    item = _bit_item("A", "", 4, duplication=2).model_copy(
        update={
            "nominal": PerCopyAddressesNominal(
                kind="ADDRESSES_PER_COPY",
                copies=(
                    (AbsAddress(kind="ABS", value=0),),
                    (AbsAddress(kind="ABS", value=4),),
                ),
            )
        }
    )
    with pytest.raises(UnsupportedDataType) as refused:
        encode_dc(item, ORIGIN)
    assert str(refused.value) == (
        "DC type AL.4 with * in its values is not supported yet — red-dragon-6uyp.97"
    )
