"""Nested literal values carried by the Data directive."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.field_name import FieldName
from interpreter.types.type_expr import TypeExpr


@dataclass(frozen=True)
class DataScalar:
    value: bool | int | str
    type_expr: TypeExpr


@dataclass(frozen=True)
class DataField:
    name: FieldName
    value: DataValue


@dataclass(frozen=True)
class DataRecord:
    fields: tuple[DataField, ...]


@dataclass(frozen=True)
class DataList:
    items: tuple[DataValue, ...]


type DataValue = DataScalar | DataRecord | DataList
