# pyright: standard
"""Typed scalars and fields for the Data the COBOL lowering declares."""

from __future__ import annotations

from interpreter.constants import FoundationTypeName
from interpreter.data_value import DataField, DataScalar, DataValue
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
