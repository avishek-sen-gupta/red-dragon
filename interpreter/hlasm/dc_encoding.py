# pyright: standard
"""Byte images of DC operands, computed when the program is assembled."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.address import Address
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.base_displacement_address import BaseDisplacementAddress
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType

type DcPiece = ConstantImage | AddressSlot
type Encoder = Callable[[str, int], tuple[int, ...]]

FLOATING_POINT_ISSUE = "red-dragon-6uyp.21"
OTHER_TYPES_ISSUE = "red-dragon-6uyp.63"
ENCODING_ISSUE = "red-dragon-6uyp.93"

_FLOATING_POINT_TYPES = frozenset({"E", "D", "L"})
_UNSPLIT_TYPES = frozenset({"C"})
_NOMINAL_SEPARATOR = ","
_DECIMAL_POINT = "."
_MINUS = "-"
_SIGNS = "+-"
_EBCDIC_SPACE = 0x40
_ZONE_NIBBLE = 0xF
_POSITIVE_SIGN = 0xC
_NEGATIVE_SIGN = 0xD
_NIBBLE_BITS = 4
_HEX_DIGITS_PER_BYTE = 2
_HEX_RADIX = 16
_BINARY_RADIX = 2


def _binary(value: int, length: int) -> tuple[int, ...]:
    return tuple((value % (1 << (BITS_PER_BYTE * length))).to_bytes(length, "big"))


def _character(text: str, length: int) -> tuple[int, ...]:
    ebcdic = tuple(EbcdicTable.ASCII_TO_EBCDIC[ord(char)] for char in text)
    return (ebcdic + (_EBCDIC_SPACE,) * length)[:length]


def _hex(text: str, length: int) -> tuple[int, ...]:
    return _binary(int(text, _HEX_RADIX), length)


def _bits(text: str, length: int) -> tuple[int, ...]:
    return _binary(int(text, _BINARY_RADIX), length)


def _fixed(text: str, length: int) -> tuple[int, ...]:
    return _binary(int(text), length)


def _digits(text: str) -> str:
    return text.lstrip(_SIGNS).replace(_DECIMAL_POINT, "")


def _sign(text: str) -> int:
    return _NEGATIVE_SIGN if text.startswith(_MINUS) else _POSITIVE_SIGN


def _packed(text: str, length: int) -> tuple[int, ...]:
    return _binary(
        (int(_digits(text), _HEX_RADIX) << _NIBBLE_BITS) | _sign(text), length
    )


def _zoned(text: str, length: int) -> tuple[int, ...]:
    digits = _digits(text).rjust(length, "0")[-length:]
    zones = (_ZONE_NIBBLE,) * (length - 1) + (_sign(text),)
    return tuple(
        (zone << _NIBBLE_BITS) | int(digit)
        for zone, digit in zip(zones, digits, strict=True)
    )


def _bytes_for(units_per_byte: int) -> Callable[[str], int]:
    return lambda text: -(-len(text) // units_per_byte)


def _fixed_width(width: int) -> Callable[[str], int]:
    return lambda _text: width


_STRING_ENCODERS: Mapping[str, Encoder] = {
    "C": _character,
    "X": _hex,
    "B": _bits,
    "F": _fixed,
    "H": _fixed,
    "P": _packed,
    "Z": _zoned,
}

_IMPLICIT_LENGTHS: Mapping[str, Callable[[str], int]] = {
    "C": len,
    "X": _bytes_for(_HEX_DIGITS_PER_BYTE),
    "B": _bytes_for(BITS_PER_BYTE),
    "F": _fixed_width(4),
    "H": _fixed_width(2),
    "P": lambda text: len(_digits(text)) // 2 + 1,
    "Z": lambda text: len(_digits(text)),
}

_ADDRESS_TYPES = frozenset({"A", "Y", "V"})

_ALIGNMENTS: Mapping[str, int] = {"F": 4, "H": 2, "A": 4, "Y": 2, "V": 4}


def _check_supported(item: DcItem) -> None:
    if item.length_unit == LengthUnit.BIT:
        raise UnsupportedDataType(
            f"{item.type}{item.extension}L.{item.length}", ENCODING_ISSUE
        )
    if item.extension == "" and (
        item.type in _STRING_ENCODERS or item.type in _ADDRESS_TYPES
    ):
        return
    issue = (
        FLOATING_POINT_ISSUE
        if item.type in _FLOATING_POINT_TYPES
        else OTHER_TYPES_ISSUE
    )
    raise UnsupportedDataType(item.type + item.extension, issue)


def _values(item: DcItem, text: str) -> tuple[str, ...]:
    if item.type in _UNSPLIT_TYPES:
        return (text,)
    return tuple(text.split(_NOMINAL_SEPARATOR))


def _string_piece(item: DcItem, text: str) -> ConstantImage:
    length = item.length if item.explicit_length else _IMPLICIT_LENGTHS[item.type](text)
    return ConstantImage(_STRING_ENCODERS[item.type](text, length))


def _assembled_address(value: AbsAddress | ExternalAddress) -> int:
    match value:
        case AbsAddress(value=number):
            return number
        case ExternalAddress():
            return 0


def _address_piece(value: Address, width: int) -> DcPiece:
    if isinstance(value, BaseDisplacementAddress):
        raise UnsupportedDataType("S", ENCODING_ISSUE)
    if isinstance(value, RelocAddress):
        return AddressSlot(value, width)
    return ConstantImage(_binary(_assembled_address(value), width))


def _operand(
    item: DcItem, nominal: StringNominal | AddressesNominal
) -> tuple[DcPiece, ...]:
    match nominal:
        case StringNominal(value=text):
            return tuple(_string_piece(item, value) for value in _values(item, text))
        case AddressesNominal(values=values):
            return tuple(_address_piece(value, item.length) for value in values)


def encode_dc(item: DcItem) -> tuple[DcPiece, ...]:
    _check_supported(item)
    if isinstance(item.nominal, OmittedNominal):
        return ()
    return _operand(item, item.nominal) * item.duplication


def dc_alignment(item: DcItem) -> int:
    if item.explicit_length:
        return 1
    return _ALIGNMENTS.get(item.type, 1)
