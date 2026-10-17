"""Sort keys of every encoding order by algebraic value; DESCENDING reverses one key."""

from __future__ import annotations

import struct
from collections.abc import Sequence

from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.sort_field import SortField
from interpreter.cobol.sort_key_encoding import SortKeyEncoding
from interpreter.cobol.sort_order import ordered
from tests.covers import covers

_NATIVE = tuple(range(256))

_ASCENDING_IMAGES: Sequence[tuple[SortKeyEncoding, Sequence[bytes]]] = (
    (
        SortKeyEncoding.ZONED_TRAILING,
        (b"\xf1\xd2", b"\xf0\xd3", b"\xf0\xc0", b"\xf0\xc7", b"\xf1\xf5"),
    ),
    (SortKeyEncoding.ZONED_LEADING, (b"\xd1\xf2", b"\xc0\xf3", b"\xf1\xf5")),
    (SortKeyEncoding.ZONED_TRAILING_SEPARATE, (b"\xf1\xf2\x60", b"\xf0\xf3\x4e")),
    (SortKeyEncoding.ZONED_LEADING_SEPARATE, (b"\x60\xf1\xf2", b"\x4e\xf0\xf3")),
    (SortKeyEncoding.PACKED, (b"\x01\x2d", b"\x00\x4b", b"\x00\x3c", b"\x00\x5f")),
    (SortKeyEncoding.BINARY_SIGNED, (b"\xff\xfe", b"\x00\x01", b"\x7f\xff")),
    (SortKeyEncoding.BINARY_UNSIGNED, (b"\x00\x01", b"\x7f\xff", b"\xff\xfe")),
    (SortKeyEncoding.FLOAT_SHORT, (struct.pack(">f", -1.5), struct.pack(">f", 0.25))),
    (SortKeyEncoding.FLOAT_LONG, (struct.pack(">d", -2.0), struct.pack(">d", 1e-3))),
)


def _field(
    encoding: SortKeyEncoding, length: int, direction: SortKeyDirection
) -> SortField:
    return SortField(offset=0, length=length, encoding=encoding, direction=direction)


@covers(CobolFeature.SORT)
def test_each_key_encoding_orders_by_value_and_descending_reverses_it() -> None:
    def order(
        encoding: SortKeyEncoding, images: Sequence[bytes], direction: SortKeyDirection
    ) -> list[bytes]:
        return ordered(
            [*images[1:], images[0]],
            [_field(encoding, len(images[0]), direction)],
            _NATIVE,
        )

    assert [
        order(encoding, images, SortKeyDirection.ASCENDING)
        for encoding, images in _ASCENDING_IMAGES
    ] == [list(images) for _, images in _ASCENDING_IMAGES]
    assert [
        order(encoding, images, SortKeyDirection.DESCENDING)
        for encoding, images in _ASCENDING_IMAGES
    ] == [list(reversed(images)) for _, images in _ASCENDING_IMAGES]
