# pyright: standard
"""Typed scalars and fields for the Data the COBOL lowering declares."""

from __future__ import annotations

from interpreter.constants import FoundationTypeName
from interpreter.data_value import (
    DataField,
    DataList,
    DataRecord,
    DataScalar,
    DataValue,
)
from interpreter.field_name import FieldName
from interpreter.types.type_expr import scalar


def text(value: str) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.STRING))


def integer(value: int) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.INT))


def boolean(value: bool) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.BOOL))


def named(name: str, value: DataValue) -> DataField:
    return DataField(FieldName(name), value)


def field_value(record: DataRecord, name: str) -> DataValue:
    return next(f.value for f in record.fields if f.name == FieldName(name))


def text_of(record: DataRecord, name: str) -> str:
    match field_value(record, name):
        case DataScalar(value=str() as value):
            return value
        case other:
            raise TypeError(f"field {name} is not text: {other!r}")


def integer_of(record: DataRecord, name: str) -> int:
    return integer_value(field_value(record, name))


def integer_value(value: DataValue) -> int:
    match value:
        case DataScalar(value=bool()) as flag:
            raise TypeError(f"not an integer: {flag!r}")
        case DataScalar(value=int() as number):
            return number
        case other:
            raise TypeError(f"not an integer: {other!r}")


def items_of(record: DataRecord, name: str) -> tuple[DataValue, ...]:
    match field_value(record, name):
        case DataList(items=items):
            return items
        case other:
            raise TypeError(f"field {name} is not a list: {other!r}")


def record_value(value: DataValue) -> DataRecord:
    match value:
        case DataRecord() as record:
            return record
        case other:
            raise TypeError(f"not a record: {other!r}")
