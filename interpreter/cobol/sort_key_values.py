"""A sort key's stored bytes read as the value its comparison orders by: numeric
keys by algebraic value, alphanumeric keys by collating weight."""

from __future__ import annotations

import struct
from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from interpreter.cobol.cobol_constants import ByteConstants
from interpreter.cobol.sort_key_encoding import SortKeyEncoding

KeyValue = tuple[float, ...]

_NEGATIVE_SIGNS = frozenset({0x0B, ByteConstants.SIGN_NIBBLE_NEGATIVE})


def _digits(nibbles: Sequence[int]) -> int:
    return reduce(lambda total, digit: total * 10 + digit, nibbles, 0)


def _signed(magnitude: int, negative: bool) -> KeyValue:
    return (-magnitude if negative else magnitude,)


def _zone(byte: int) -> int:
    return byte >> 4


def _low(image: bytes) -> list[int]:
    return [b & ByteConstants.NIBBLE_MASK for b in image]


def _collated(image: bytes, weights: Sequence[int]) -> KeyValue:
    return tuple(weights[b] for b in image)


def _zoned_trailing(image: bytes, weights: Sequence[int]) -> KeyValue:
    return _signed(_digits(_low(image)), _zone(image[-1]) in _NEGATIVE_SIGNS)


def _zoned_leading(image: bytes, weights: Sequence[int]) -> KeyValue:
    return _signed(_digits(_low(image)), _zone(image[0]) in _NEGATIVE_SIGNS)


def _zoned_trailing_separate(image: bytes, weights: Sequence[int]) -> KeyValue:
    return _signed(_digits(_low(image[:-1])), image[-1] == ByteConstants.EBCDIC_MINUS)


def _zoned_leading_separate(image: bytes, weights: Sequence[int]) -> KeyValue:
    return _signed(_digits(_low(image[1:])), image[0] == ByteConstants.EBCDIC_MINUS)


def _packed(image: bytes, weights: Sequence[int]) -> KeyValue:
    nibbles = [n for b in image for n in (_zone(b), b & ByteConstants.NIBBLE_MASK)]
    return _signed(_digits(nibbles[:-1]), nibbles[-1] in _NEGATIVE_SIGNS)


def _binary_signed(image: bytes, weights: Sequence[int]) -> KeyValue:
    return (int.from_bytes(image, "big", signed=True),)


def _binary_unsigned(image: bytes, weights: Sequence[int]) -> KeyValue:
    return (int.from_bytes(image, "big", signed=False),)


def _float_short(image: bytes, weights: Sequence[int]) -> KeyValue:
    return struct.unpack(">f", image)


def _float_long(image: bytes, weights: Sequence[int]) -> KeyValue:
    return struct.unpack(">d", image)


KEY_VALUES: Mapping[SortKeyEncoding, Callable[[bytes, Sequence[int]], KeyValue]] = {
    SortKeyEncoding.ALPHANUMERIC: _collated,
    SortKeyEncoding.ZONED_TRAILING: _zoned_trailing,
    SortKeyEncoding.ZONED_LEADING: _zoned_leading,
    SortKeyEncoding.ZONED_TRAILING_SEPARATE: _zoned_trailing_separate,
    SortKeyEncoding.ZONED_LEADING_SEPARATE: _zoned_leading_separate,
    SortKeyEncoding.PACKED: _packed,
    SortKeyEncoding.BINARY_SIGNED: _binary_signed,
    SortKeyEncoding.BINARY_UNSIGNED: _binary_unsigned,
    SortKeyEncoding.FLOAT_SHORT: _float_short,
    SortKeyEncoding.FLOAT_LONG: _float_long,
}
