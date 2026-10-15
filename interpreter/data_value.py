"""Nested literal values carried by the Data directive."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.field_name import FieldName
from interpreter.shared_on_deepcopy import SharedOnDeepcopy
from interpreter.types.type_expr import TypeExpr


@dataclass(frozen=True)
class DataScalar(SharedOnDeepcopy):
    value: bool | int | str
    type_expr: TypeExpr


@dataclass(frozen=True)
class DataField(SharedOnDeepcopy):
    name: FieldName
    value: DataValue


@dataclass(frozen=True)
class DataRecord(SharedOnDeepcopy):
    fields: tuple[DataField, ...]


@dataclass(frozen=True)
class DataList(SharedOnDeepcopy):
    items: tuple[DataValue, ...]


type DataValue = DataScalar | DataRecord | DataList
