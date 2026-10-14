# pyright: standard
"""The data-layout Data: each WORKING-STORAGE field's position, written and read back."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.data_literals import boolean, integer, named, text
from interpreter.cobol.field_position import FieldPosition
from interpreter.data_value import DataList, DataRecord, DataScalar, DataValue
from interpreter.field_name import FieldName
from interpreter.instructions import Data
from interpreter.var_name import VarName

DATA_LAYOUT = VarName("__cobol_data_layout")


def _entry(field: FieldLayout) -> DataRecord:
    descriptor = field.type_descriptor
    return DataRecord(
        (
            named("name", text(field.name)),
            named("offset", integer(field.offset)),
            named("length", integer(field.byte_length)),
            named("category", text(descriptor.category.value)),
            named("total_digits", integer(descriptor.total_digits)),
            named("decimal_digits", integer(descriptor.decimal_digits)),
            named("signed", boolean(descriptor.signed)),
        )
    )


def layout_data(fields: Iterable[FieldLayout]) -> Data:
    entries = DataList(tuple(_entry(f) for f in fields))
    return Data(name=DATA_LAYOUT, value=DataRecord((named("fields", entries),)))


def _value(record: DataRecord, name: str) -> DataValue:
    return next(f.value for f in record.fields if f.name == FieldName(name))


def _str(record: DataRecord, name: str) -> str:
    match _value(record, name):
        case DataScalar(value=str() as value):
            return value
        case other:
            raise TypeError(f"layout field {name} is not text: {other!r}")


def _int(record: DataRecord, name: str) -> int:
    match _value(record, name):
        case DataScalar(value=int() as value):
            return value
        case other:
            raise TypeError(f"layout field {name} is not an integer: {other!r}")


def _bool(record: DataRecord, name: str) -> bool:
    match _value(record, name):
        case DataScalar(value=bool() as value):
            return value
        case other:
            raise TypeError(f"layout field {name} is not a boolean: {other!r}")


def _records(value: DataValue) -> tuple[DataRecord, ...]:
    match value:
        case DataList(items=items):
            return tuple(_record(i) for i in items)
        case other:
            raise TypeError(f"layout fields are not a list: {other!r}")


def _record(value: DataValue) -> DataRecord:
    match value:
        case DataRecord():
            return value
        case other:
            raise TypeError(f"layout entry is not a record: {other!r}")


def _position(entry: DataRecord) -> FieldPosition:
    return FieldPosition(
        offset=_int(entry, "offset"),
        length=_int(entry, "length"),
        category=_str(entry, "category"),
        total_digits=_int(entry, "total_digits"),
        decimal_digits=_int(entry, "decimal_digits"),
        signed=_bool(entry, "signed"),
    )


def field_positions(declarations: Sequence[Data]) -> Mapping[str, FieldPosition]:
    return {
        _str(entry, "name"): _position(entry)
        for d in declarations
        if d.name == DATA_LAYOUT
        for entry in _records(_value(_record(d.value), "fields"))
    }
