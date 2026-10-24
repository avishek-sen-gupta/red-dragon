"""Self-describing JSON for red-dragon IR values: instructions, type expressions, refs and tables."""

from __future__ import annotations

import dataclasses
import enum
import json
import typing
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from cobol_numeric.number import CobolNumber, from_text, to_text
from interpreter.class_name import NO_CLASS_NAME, ClassName, NoClassName
from interpreter.constants import Language
from interpreter.continuation_name import (
    NO_CONTINUATION_NAME,
    ContinuationName,
    NoContinuationName,
)
from interpreter.data_value import DataField, DataList, DataRecord, DataScalar
from interpreter.field_name import NO_FIELD_NAME, FieldKind, FieldName, NoFieldName
from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)
from interpreter.func_name import NO_FUNC_NAME, FuncName, NoFuncName
from interpreter.instructions import Instruction
from interpreter.ir import (
    NO_LABEL,
    CodeLabel,
    NoCodeLabel,
    SourceLocation,
    SpreadArguments,
)
from interpreter.operator_kind import BinopKind, UnopKind
from interpreter.path_name import NO_PATH_NAME, NoPathName, PathName
from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.dc_warning_kind import DcWarningKind
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.in_macro import InMacro
from interpreter.project.in_open_code import InOpenCode
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.types import ExportTable, ImportKind, ImportRef, ModuleUnit
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.project.unit_format_error import UnitFormatError
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import NO_REGISTER, NoRegister, Register
from interpreter.type_name import TypeName
from interpreter.types import type_expr as te
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.var_scope_info import VarScopeInfo
from interpreter.var_name import NO_VAR_NAME, NoVarName, VarName

type Wire = bool | int | float | str | list[Wire] | dict[str, Wire]

_DATACLASSES: tuple[type, ...] = (
    *typing.get_args(Instruction),
    SpreadArguments,
    DataScalar,
    DataField,
    DataRecord,
    DataList,
    Register,
    CodeLabel,
    VarName,
    FieldName,
    FuncName,
    ContinuationName,
    PathName,
    ClassName,
    TypeName,
    te.ScalarType,
    te.EnumType,
    te.AnnotationType,
    te.StructPatternType,
    te.ParameterizedType,
    te.FunctionType,
    te.UnionType,
    te.TypeVar,
    FuncRef,
    ClassRef,
    ImportRef,
    ExportTable,
    ModuleUnit,
    UnitDiagnostic,
    DiagnosticPlace,
    CodedDiagnostic,
    SeverityMnote,
    CommentMnote,
    ConstantDiagnostic,
    InMacro,
    InOpenCode,
    FieldInfo,
    FunctionInfo,
    ClassInfo,
    SymbolTable,
    VarScopeInfo,
    TypeEnvironmentBuilder,
)
_SINGLETONS: Mapping[type, object] = {
    NoRegister: NO_REGISTER,
    NoCodeLabel: NO_LABEL,
    NoVarName: NO_VAR_NAME,
    NoFieldName: NO_FIELD_NAME,
    NoFuncName: NO_FUNC_NAME,
    NoContinuationName: NO_CONTINUATION_NAME,
    NoPathName: NO_PATH_NAME,
    NoClassName: NO_CLASS_NAME,
}
_ENUMS: tuple[type[enum.Enum], ...] = (
    BinopKind,
    UnopKind,
    FieldKind,
    ImportKind,
    Language,
    DiagnosticSeverity,
    DcWarningKind,
)
_NATIVE = (bool, int, float, str)


class IrCodec:
    """Encodes values to JSON-ready data and decodes them back to the same types."""

    def __init__(self) -> None:
        self._classes: Mapping[str, type] = {
            cls.__name__: cls for cls in (*_DATACLASSES, *_SINGLETONS)
        }
        self._enums: Mapping[str, type[enum.Enum]] = {e.__name__: e for e in _ENUMS}
        self._encoders: tuple[
            tuple[type | tuple[type, ...], Callable[[object], Wire]], ...
        ] = (
            (enum.Enum, self._enum),
            (type(None), lambda _v: self._tagged("none", 0)),
            (_NATIVE, self._native),
            (CobolNumber, self._number),
            (bytes, self._bytes),
            (Path, lambda v: self._tagged("path", str(v))),
            (tuple, lambda v: self._tagged("tuple", self._list(v))),
            (frozenset, self._frozenset),
            (list, self._list),
            (dict, self._dict),
            (SourceLocation, self._loc),
            (te.UnknownType, lambda _v: self._tagged("unknown_type", 0)),
        )
        self._decoders: Mapping[str, Callable[[Wire], object]] = {
            "enum": self._decode_enum,
            "decimal": lambda v: from_text(str(v)),
            "bytes": lambda v: bytes.fromhex(str(v)),
            "path": lambda v: Path(str(v)),
            "tuple": lambda v: tuple(self._items(v)),
            "frozenset": lambda v: frozenset(self._items(v)),
            "dict": self._decode_dict,
            "loc": self._decode_loc,
            "unknown_type": lambda _v: te.UNKNOWN,
            "none": lambda _v: None,
            "dc": self._decode_dataclass,
        }

    def encode(self, value: object) -> Wire:
        encoder = next(
            (enc for kind, enc in self._encoders if isinstance(value, kind)),
            self._dataclass,
        )
        return encoder(value)

    def decode_as[T](self, wire: Wire, cls: type[T]) -> T:
        value = self.decode(wire)
        if isinstance(value, cls):
            return value
        raise UnitFormatError(f"expected {cls.__name__}, found {type(value).__name__}")

    def decode(self, wire: Wire) -> object:
        match wire:
            case list():
                return [self.decode(item) for item in wire]
            case {"$": str(kind), "v": payload}:
                return self._decoder(kind)(payload)
            case _:
                return wire

    def _tagged(self, kind: str, payload: Wire) -> Wire:
        return {"$": kind, "v": payload}

    def _native(self, value: object) -> Wire:
        match value:
            case bool() | int() | float() | str():
                return value
            case _:
                raise UnitFormatError(f"not a JSON value: {value!r}")

    def _enum(self, value: object) -> Wire:
        match value:
            case enum.Enum():
                return self._tagged(
                    "enum", {"c": type(value).__name__, "v": self.encode(value.value)}
                )
            case _:
                raise UnitFormatError(f"not an enum: {value!r}")

    def _number(self, value: object) -> Wire:
        match value:
            case CobolNumber():
                return self._tagged("decimal", to_text(value))
            case _:
                raise UnitFormatError(f"not a COBOL number: {value!r}")

    def _bytes(self, value: object) -> Wire:
        match value:
            case bytes():
                return self._tagged("bytes", value.hex())
            case _:
                raise UnitFormatError(f"not bytes: {value!r}")

    def _list(self, value: object) -> Wire:
        match value:
            case list() | tuple():
                return [self.encode(item) for item in value]
            case _:
                raise UnitFormatError(f"not a sequence: {value!r}")

    def _frozenset(self, value: object) -> Wire:
        match value:
            case frozenset():
                by_text = {json.dumps(wire): wire for wire in map(self.encode, value)}
                ordered: list[Wire] = [by_text[text] for text in sorted(by_text)]
                return self._tagged("frozenset", ordered)
            case _:
                raise UnitFormatError(f"not a frozenset: {value!r}")

    def _dict(self, value: object) -> Wire:
        match value:
            case dict():
                pairs: list[Wire] = [
                    [self.encode(name), self.encode(item)]
                    for name, item in value.items()
                ]
                return self._tagged("dict", pairs)
            case _:
                raise UnitFormatError(f"not a dict: {value!r}")

    def _loc(self, value: object) -> Wire:
        match value:
            case SourceLocation():
                return self._tagged(
                    "loc",
                    [value.start_line, value.start_col, value.end_line, value.end_col],
                )
            case _:
                raise UnitFormatError(f"not a source location: {value!r}")

    def _dataclass(self, value: object) -> Wire:
        match value:
            case _ if dataclasses.is_dataclass(value) and not isinstance(value, type):
                fields = {
                    f.name: self.encode(getattr(value, f.name))
                    for f in dataclasses.fields(value)
                }
                return self._tagged("dc", {"c": type(value).__name__, "v": fields})
            case _:
                raise UnitFormatError(f"no codec for {type(value).__name__}: {value!r}")

    def _decoder(self, kind: str) -> Callable[[Wire], object]:
        match self._decoders.get(kind):
            case None:
                raise UnitFormatError(f"unknown kind {kind!r}")
            case decoder:
                return decoder

    def _items(self, wire: Wire) -> Sequence[object]:
        match wire:
            case list():
                return [self.decode(item) for item in wire]
            case _:
                raise UnitFormatError(f"expected a list, found {wire!r}")

    def _decode_enum(self, wire: Wire) -> object:
        match wire:
            case {"c": str(name), "v": value} if name in self._enums:
                return self._enums[name](self.decode(value))
            case _:
                raise UnitFormatError(f"unknown enum {wire!r}")

    def _decode_dict(self, wire: Wire) -> object:
        match wire:
            case list():
                return dict(self._pair(item) for item in wire)
            case _:
                raise UnitFormatError(f"expected dict pairs, found {wire!r}")

    def _pair(self, wire: Wire) -> tuple[object, object]:
        match wire:
            case [name, value]:
                return self.decode(name), self.decode(value)
            case _:
                raise UnitFormatError(f"expected a pair, found {wire!r}")

    def _decode_loc(self, wire: Wire) -> object:
        match wire:
            case [int(start_line), int(start_col), int(end_line), int(end_col)]:
                return SourceLocation(
                    start_line=start_line,
                    start_col=start_col,
                    end_line=end_line,
                    end_col=end_col,
                )
            case _:
                raise UnitFormatError(f"expected a source location, found {wire!r}")

    def _decode_dataclass(self, wire: Wire) -> object:
        match wire:
            case {"c": str(name), "v": dict(fields)} if name in self._classes:
                return self._construct(self._classes[name], fields)
            case {"c": str(name)}:
                raise UnitFormatError(f"unknown class {name!r}")
            case _:
                raise UnitFormatError(f"expected a dataclass, found {wire!r}")

    def _construct(self, cls: type, fields: Mapping[str, Wire]) -> object:
        match _SINGLETONS.get(cls):
            case None:
                return cls(
                    **{name: self.decode(value) for name, value in fields.items()}
                )
            case singleton:
                return singleton
