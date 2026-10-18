"""How a SORT or MERGE orders its work file: the keys, major to minor, and the
collating weights alphanumeric keys compare by."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.data_literals import (
    integer,
    integer_value,
    items_of,
    named,
    record_value,
)
from interpreter.cobol.sort_field import SortField, sort_field_of
from interpreter.data_value import DataList, DataRecord


@dataclass(frozen=True)
class SortOrdering:
    fields: tuple[SortField, ...]
    weights: tuple[int, ...]

    def data(self) -> DataRecord:
        return DataRecord(
            (
                named("fields", DataList(tuple(f.data() for f in self.fields))),
                named("weights", DataList(tuple(integer(w) for w in self.weights))),
            )
        )


def ordering_of(record: DataRecord) -> SortOrdering:
    return SortOrdering(
        fields=tuple(
            sort_field_of(record_value(item)) for item in items_of(record, "fields")
        ),
        weights=tuple(integer_value(item) for item in items_of(record, "weights")),
    )
