"""A sort key as the work file sees it: where it sits in a record and how it orders."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.sort_key_encoding import SortKeyEncoding


@dataclass(frozen=True)
class SortField:
    offset: int
    length: int
    encoding: SortKeyEncoding
    direction: SortKeyDirection

    def image(self, record: bytes) -> bytes:
        return record[self.offset : self.offset + self.length]


_ARGUMENTS_PER_FIELD = 4


def _field(arguments: Sequence[int | str]) -> SortField:
    offset, length, encoding, direction = arguments
    return SortField(
        offset=int(offset),
        length=int(length),
        encoding=SortKeyEncoding(encoding),
        direction=SortKeyDirection(direction),
    )


def sort_fields(arguments: Sequence[int | str]) -> tuple[SortField, ...]:
    return tuple(
        _field(arguments[start : start + _ARGUMENTS_PER_FIELD])
        for start in range(0, len(arguments), _ARGUMENTS_PER_FIELD)
    )


def sort_field_arguments(sort_field: SortField) -> tuple[int | str, ...]:
    return (
        sort_field.offset,
        sort_field.length,
        sort_field.encoding.value,
        sort_field.direction.value,
    )
