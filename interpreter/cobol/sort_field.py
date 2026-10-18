"""A sort key as the work file sees it: where it sits in a record and how it orders."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.data_literals import integer, integer_of, named, text, text_of
from interpreter.cobol.sort_key_encoding import SortKeyEncoding
from interpreter.data_value import DataRecord


@dataclass(frozen=True)
class SortField:
    offset: int
    length: int
    encoding: SortKeyEncoding
    direction: SortKeyDirection

    def image(self, record: bytes) -> bytes:
        return record[self.offset : self.offset + self.length]

    def data(self) -> DataRecord:
        return DataRecord(
            (
                named("offset", integer(self.offset)),
                named("length", integer(self.length)),
                named("encoding", text(self.encoding.value)),
                named("direction", text(self.direction.value)),
            )
        )


def sort_field_of(record: DataRecord) -> SortField:
    return SortField(
        offset=integer_of(record, "offset"),
        length=integer_of(record, "length"),
        encoding=SortKeyEncoding(text_of(record, "encoding")),
        direction=SortKeyDirection(text_of(record, "direction")),
    )
