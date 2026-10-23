# pyright: standard
"""Byte images of DC operands, computed when the program is assembled."""

from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from itertools import chain
from math import floor

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.address import Address
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.base_displacement_address import BaseDisplacementAddress
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.origin import Origin
from hlasm_asg.program.per_copy_addresses_nominal import PerCopyAddressesNominal
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.hlasm.address_slot import AddressSlot
from interpreter.hlasm.bit_length_image import BitLengthImage
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_value_out_of_range import DcValueOutOfRange
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType

type DcPiece = ConstantImage | AddressSlot
type Encoder = Callable[[str, int], int]

FLOATING_POINT_ISSUE = "red-dragon-6uyp.94"
LINKER_TYPES_ISSUE = "red-dragon-6uyp.96"
OTHER_TYPES_ISSUE = "red-dragon-6uyp.63"
ENCODING_ISSUE = "red-dragon-6uyp.93"
BIT_LENGTH_STAR_ISSUE = "red-dragon-6uyp.97"

_FLOATING_POINT_TYPES = frozenset({"E", "D", "L"})
_LINKER_TYPES = frozenset({"Q", "J"})
_UNSPLIT_TYPES = frozenset({"C"})
_NOMINAL_SEPARATOR = ","
_DECIMAL_POINT = "."
_MINUS = "-"
_SIGNS = "+-"
_EBCDIC_SPACE = (0x40,)
_ASCII_SPACE = (0x20,)
_UNICODE_SPACE = (0x00, 0x20)
_ZONE_NIBBLE = 0xF
_POSITIVE_SIGN = 0xC
_NEGATIVE_SIGN = 0xD
_NIBBLE_BITS = 4
_HEX_DIGITS_PER_BYTE = 2
_HEX_RADIX = 16
_BINARY_RADIX = 2
_BASE_SHIFT = 12
_LONG_BASE_SHIFT = 20
_LOW_DISPLACEMENT_MASK = 0xFFF
_HIGH_DISPLACEMENT_MASK = 0xFF
_LOW_DISPLACEMENT_SHIFT = 8
_UNSIGNED = "U"
_SPACE = " "
_HALF = Fraction(1, 2)
_DECIMAL_BASE = Fraction(10)
_BINARY_BASE = Fraction(2)


def _bytes_of(bits: int) -> int:
    return -(-bits // BITS_PER_BYTE)


def _truncated(value: int, bits: int) -> int:
    return value % (1 << bits)


def _ebcdic(text: str) -> tuple[int, ...]:
    return tuple(EbcdicTable.ASCII_TO_EBCDIC[ord(char)] for char in text)


def _ascii(text: str) -> tuple[int, ...]:
    return tuple(ord(char) for char in text)


def _unicode(text: str) -> tuple[int, ...]:
    return tuple(text.encode("utf-16-be"))


def _characters(
    code: Callable[[str], tuple[int, ...]], space: tuple[int, ...]
) -> Encoder:
    def encode(text: str, bits: int) -> int:
        size = _bytes_of(bits)
        image = (code(text) + space * size)[:size]
        return int.from_bytes(bytes(image), "big") >> (size * BITS_PER_BYTE - bits)

    return encode


def _hex(text: str, bits: int) -> int:
    return _truncated(int(text, _HEX_RADIX), bits)


def _binary(text: str, bits: int) -> int:
    return _truncated(int(text, _BINARY_RADIX), bits)


def _digits(text: str) -> str:
    return text.lstrip(_SIGNS).replace(_DECIMAL_POINT, "")


def _sign(text: str) -> int:
    return _NEGATIVE_SIGN if text.startswith(_MINUS) else _POSITIVE_SIGN


def _packed(text: str, bits: int) -> int:
    return _truncated(
        (int(_digits(text), _HEX_RADIX) << _NIBBLE_BITS) | _sign(text), bits
    )


def _zoned(text: str, bits: int) -> int:
    size = _bytes_of(bits)
    digits = _digits(text).rjust(size, "0")[-size:]
    zones = (_ZONE_NIBBLE,) * (size - 1) + (_sign(text),)
    image = bytes(
        (zone << _NIBBLE_BITS) | int(digit)
        for zone, digit in zip(zones, digits, strict=True)
    )
    return _truncated(int.from_bytes(image, "big"), bits)


def _bytes_for(units_per_byte: int) -> Callable[[str], int]:
    return lambda text: -(-len(text) // units_per_byte)


_STRING_ENCODERS: Mapping[str, Encoder] = {
    "C": _characters(_ebcdic, _EBCDIC_SPACE),
    "CE": _characters(_ebcdic, _EBCDIC_SPACE),
    "CA": _characters(_ascii, _ASCII_SPACE),
    "CU": _characters(_unicode, _UNICODE_SPACE),
    "X": _hex,
    "B": _binary,
    "P": _packed,
    "Z": _zoned,
}

_VALUE_LENGTHS: Mapping[str, Callable[[str], int]] = {
    "X": _bytes_for(_HEX_DIGITS_PER_BYTE),
    "B": _bytes_for(BITS_PER_BYTE),
    "P": lambda text: len(_digits(text)) // 2 + 1,
    "Z": lambda text: len(_digits(text)),
}

_ADDRESS_TYPES = frozenset({"A", "AD", "Y", "V", "VD", "S", "SY"})
_FIXED_POINT_TYPES = frozenset({"F", "FD", "H"})
_SUPPORTED_TYPES = _STRING_ENCODERS.keys() | _ADDRESS_TYPES | _FIXED_POINT_TYPES


def _code(item: DcItem) -> str:
    return item.type + item.extension


def _issue(item: DcItem) -> str:
    if item.type in _FLOATING_POINT_TYPES:
        return FLOATING_POINT_ISSUE
    if item.type in _LINKER_TYPES:
        return LINKER_TYPES_ISSUE
    return OTHER_TYPES_ISSUE


def _check_supported(item: DcItem) -> None:
    if _code(item) in _SUPPORTED_TYPES:
        return
    raise UnsupportedDataType(_code(item), _issue(item))


def _fixed_value(item: DcItem, text: str) -> int:
    number = Fraction(text.replace(_SPACE, "").removeprefix(_UNSIGNED))
    scaled = abs(number) * _DECIMAL_BASE**item.exponent * _BINARY_BASE**item.scale
    magnitude = floor(scaled + _HALF)
    return -magnitude if number < 0 else magnitude


def _fixed_range(text: str, bits: int) -> range:
    if text.startswith(_UNSIGNED):
        return range(1 << bits)
    return range(-(1 << (bits - 1)), 1 << (bits - 1))


def _fixed(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    value = _fixed_value(item, text)
    if value not in _fixed_range(text, bits):
        raise DcValueOutOfRange(f"{_code(item)}'{text}'", origin)
    return _truncated(value, bits)


def _string_value(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    if _code(item) in _FIXED_POINT_TYPES:
        return _fixed(item, text, bits, origin)
    return _STRING_ENCODERS[_code(item)](text, bits)


def _values(item: DcItem, text: str) -> tuple[str, ...]:
    if item.type in _UNSPLIT_TYPES:
        return (text,)
    return tuple(text.split(_NOMINAL_SEPARATOR))


def _image(value: int, length: int) -> ConstantImage:
    return ConstantImage(tuple(value.to_bytes(length, "big")))


def _string_piece(item: DcItem, text: str, origin: Origin) -> ConstantImage:
    code = _code(item)
    length = (
        _VALUE_LENGTHS[code](text)
        if code in _VALUE_LENGTHS and not item.explicit_length
        else item.length
    )
    return _image(_string_value(item, text, length * BITS_PER_BYTE, origin), length)


def _base_displacement(item: DcItem, base: int, displacement: int) -> int:
    if item.extension == "":
        return (base << _BASE_SHIFT) | displacement
    low = displacement & _LOW_DISPLACEMENT_MASK
    high = (displacement >> _BASE_SHIFT) & _HIGH_DISPLACEMENT_MASK
    return (base << _LONG_BASE_SHIFT) | (low << _LOW_DISPLACEMENT_SHIFT) | high


def _assembled_address(
    item: DcItem, value: AbsAddress | BaseDisplacementAddress
) -> int:
    match value:
        case AbsAddress(value=number):
            return _truncated(number, item.length * BITS_PER_BYTE)
        case BaseDisplacementAddress(base=base, displacement=displacement):
            return _base_displacement(item, base, displacement)


def _address_piece(item: DcItem, value: Address) -> DcPiece:
    if isinstance(value, RelocAddress):
        return AddressSlot(value, item.length)
    if isinstance(value, ExternalAddress):
        return _image(0, item.length)
    return _image(_assembled_address(item, value), item.length)


def _address_pieces(item: DcItem, values: Sequence[Address]) -> tuple[DcPiece, ...]:
    return tuple(_address_piece(item, value) for value in values)


def _operand(
    item: DcItem, nominal: StringNominal | AddressesNominal, origin: Origin
) -> tuple[DcPiece, ...]:
    match nominal:
        case StringNominal(value=text):
            return tuple(
                _string_piece(item, value, origin) for value in _values(item, text)
            )
        case AddressesNominal(values=values):
            return _address_pieces(item, values)


def _copies(
    item: DcItem,
    nominal: StringNominal | AddressesNominal | PerCopyAddressesNominal,
    origin: Origin,
) -> tuple[DcPiece, ...]:
    match nominal:
        case PerCopyAddressesNominal(copies=copies):
            return tuple(
                chain.from_iterable(_address_pieces(item, values) for values in copies)
            )
        case once:
            return _operand(item, once, origin) * item.duplication


def _bit_address(item: DcItem, value: Address) -> int:
    if isinstance(value, AbsAddress):
        return _truncated(value.value, item.length)
    raise HlasmLoweringError(
        f"{_code(item)}L.{item.length}", "an absolute value", value.kind
    )


def _bit_values(
    item: DcItem, nominal: StringNominal | AddressesNominal, origin: Origin
) -> tuple[int, ...]:
    match nominal:
        case StringNominal(value=text):
            return tuple(
                _string_value(item, value, item.length, origin)
                for value in _values(item, text)
            )
        case AddressesNominal(values=values):
            return tuple(_bit_address(item, value) for value in values)


def _bit_image(
    item: DcItem,
    nominal: StringNominal | AddressesNominal | PerCopyAddressesNominal,
    origin: Origin,
) -> BitLengthImage:
    match nominal:
        case PerCopyAddressesNominal():
            raise UnsupportedDataType(
                f"{_code(item)}L.{item.length} with * in its values",
                BIT_LENGTH_STAR_ISSUE,
            )
        case once:
            values = _bit_values(item, once, origin)
            return BitLengthImage(values * item.duplication, item.length)


def encode_dc(item: DcItem, origin: Origin) -> tuple[DcPiece, ...] | BitLengthImage:
    _check_supported(item)
    if isinstance(item.nominal, OmittedNominal):
        return ()
    if item.length_unit == LengthUnit.BIT:
        return _bit_image(item, item.nominal, origin)
    return _copies(item, item.nominal, origin)
