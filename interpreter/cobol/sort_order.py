"""Orders sort work-file records by their keys, major to minor, keeping equal-keyed
records in the order they were released."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import cmp_to_key, partial

from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.sort_field import SortField
from interpreter.cobol.sort_key_encoding import SortKeyEncoding

KeyValue = tuple[int, ...]

_DIRECTION_SIGN: Mapping[SortKeyDirection, int] = {
    SortKeyDirection.ASCENDING: 1,
    SortKeyDirection.DESCENDING: -1,
}


def _collated(image: bytes, weights: Sequence[int]) -> KeyValue:
    return tuple(weights[b] for b in image)


_VALUES: Mapping[SortKeyEncoding, Callable[[bytes, Sequence[int]], KeyValue]] = {
    SortKeyEncoding.ALPHANUMERIC: _collated,
}


def _value(sort_field: SortField, record: bytes, weights: Sequence[int]) -> KeyValue:
    return _VALUES[sort_field.encoding](sort_field.image(record), weights)


def _compare_field(
    weights: Sequence[int], sort_field: SortField, left: bytes, right: bytes
) -> int:
    a, b = _value(sort_field, left, weights), _value(sort_field, right, weights)
    return ((a > b) - (a < b)) * _DIRECTION_SIGN[sort_field.direction]


def _compare(
    fields: Sequence[SortField], weights: Sequence[int], left: bytes, right: bytes
) -> int:
    return next(
        (
            order
            for order in (_compare_field(weights, f, left, right) for f in fields)
            if order
        ),
        0,
    )


def ordered(
    records: Sequence[bytes], fields: Sequence[SortField], weights: Sequence[int]
) -> list[bytes]:
    return sorted(records, key=cmp_to_key(partial(_compare, fields, weights)))
