# COBOL Separate Compilation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** COBOL compilation runs as three stages chained only through files — parse to `.ast.json`, lower to `.unit.json`, link to `.linked.json` — and `compile_cobol` returns the `LinkedProgram` read back from disk, so a program lowered once can be linked and run by any later process.

**Architecture:** A language-neutral `IrCodec` encodes red-dragon values as self-describing JSON (each non-JSON value tagged with its kind; dataclasses field by field from their own field list). `UnitCodec` and `LinkedCodec` own the two file formats. `cobol_compile.py` gains `parse_stage`, `lower_stage` and `link_stage`, each skipping a program whose output file already exists; file names carry a digest of the source bytes and the lowering settings.

**Tech Stack:** Python 3.13, uv, pytest, red-dragon IR (`interpreter/`), ProLeap bridge JAR (`PROLEAP_BRIDGE_JAR`), the forge (`~/code/red-dragon-forge`) for the downstream task.

**Spec:** `docs/superpowers/specs/2026-10-13-cobol-separate-compilation-design.md`

## Global Constraints

- Stages are chained only through files, inside one `compile_cobol` call as well.
- No cache invalidation: a stage skips a program whose output file exists.
- File names: `<stem>-<digest>.<kind>.json`; the digest covers source bytes, LP mode, extension strategy names, tolerant mode and copybook directories.
- The linked file holds every `LinkedProgram` field but `merged_cfg` and `merged_registry`, which `LinkedCodec.read` rebuilds.
- red-dragon's lint ratchet (`fp-baseline.json`) must not rise: no `Any`, complexity ≤ 3 and ≤ 10 statements per function, no mutation in loops. `object` is permitted by red-dragon's rule set.
- The codec's wire values have one private type, `_Wire` (`None | bool | int | float | str | list[_Wire] | dict[str, _Wire]`), used only inside the three codec modules — the JSON boundary the codec exists to parse. Flagged for review: this is the one place a recursive JSON alias appears.
- `vendor/red-dragon` in the forge is never edited; red-dragon changes land in `~/code/red-dragon`, then the forge bumps the submodule.
- Talisman flags some ordinary words in prose; reword prose, keep identifier names.

## Review Focus

1. A `Const` whose value is a `Decimal`, a `list[int]` or `bytes` (COBOL emits all three) — must decode to the same type, not a float or a list of something else.
2. A `NO_REGISTER`/`NO_LABEL`/`NO_*_NAME` field — must decode to the sentinel class, because handlers test `is_present()` and `isinstance`, and `NO_REGISTER == Register("")` hides a wrong decode from `==`.
3. `CallWithMemory.location` holding a `VarName` versus a `Register` — must decode to the same class it was written as.
4. The same main program compiled twice in one work directory with an edited source, and then with different settings — each must produce new files, not reuse the old ones.
5. A callee that fails to lower — no unit file, the link proceeds without it, and a second compile does not mistake its absence for anything.

Pinned in Task 1 (1, 2, 3) and Task 4 (4, 5).

---

### Task 1: `IrCodec` — self-describing JSON for IR values

**Files:**
- Create: `interpreter/project/unit_format_error.py`
- Create: `interpreter/project/ir_codec.py`
- Test: `tests/unit/project/test_ir_codec.py`

**Interfaces:**
- Produces: `UnitFormatError(Exception)`; `IrCodec()` with `encode(value: object) -> _Wire` and `decode(wire: _Wire) -> object`.

Wire shape: JSON-native values (`None`, `bool`, `int`, `float`, `str`, lists) stand for themselves; every other value is `{"$": <kind>, "v": <payload>}` with kinds `enum` (`{"c": class, "v": value}`), `decimal`, `bytes` (hex), `path`, `tuple`, `frozenset` (items sorted by their JSON text), `dict` (list of `[name, value]` pairs, where a name may be any value), `loc` (four ints), `unknown_type`, and `dc` (`{"c": class name, "v": {field: value}}`). Sentinel classes (`NoRegister`, `NoCodeLabel`, `NoVarName`, `NoFieldName`, `NoFuncName`, `NoContinuationName`, `NoPathName`, `NoClassName`) decode to their singletons. Enum is checked before `str`/`int` (`BinopKind` and `Language` are `str` subclasses); `bool` is JSON-native and checked before `int` implicitly by staying native.

- [ ] **Step 1: Write the failing tests**

`tests/unit/project/test_ir_codec.py`:

```python
"""IrCodec round-trips every instruction, type expression and table exactly."""

import json
import typing
from decimal import Decimal
from pathlib import Path

import pytest

from interpreter.class_name import NO_CLASS_NAME, ClassName
from interpreter.continuation_name import ContinuationName
from interpreter.field_name import NO_FIELD_NAME, FieldKind, FieldName
from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo, SymbolTable
from interpreter.func_name import NO_FUNC_NAME, FuncName
from interpreter.instructions import (
    AddressOf, AllocRegion, Binop, Branch, BranchIf, CallCtorFunction, CallFunction,
    CallMethod, CallUnknown, CallWithMemory, Const, DeclVar, Halt_, ImportModule,
    Instruction, Label_, LoadField, LoadFieldIndirect, LoadIndex, LoadIndirect, LoadRegion,
    LoadVar, NewArray, NewObject, ResumeContinuation, Return_, SetContinuation, StoreField,
    StoreIndex, StoreIndirect, StoreVar, Suspend, Symbolic, Throw_, TryPop, TryPush, Unop,
    WriteRegion,
)
from interpreter.ir import NO_LABEL, CodeLabel, NoCodeLabel, SourceLocation, SpreadArguments
from interpreter.operator_kind import BinopKind, UnopKind
from interpreter.path_name import PathName
from interpreter.project.ir_codec import IrCodec
from interpreter.project.types import ExportTable, ImportKind, ImportRef
from interpreter.project.unit_format_error import UnitFormatError
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import NO_REGISTER, NoRegister, Register
from interpreter.type_name import TypeName
from interpreter.types import type_expr as te
from interpreter.var_name import NO_VAR_NAME, VarName
from tests.covers import NotLanguageFeature, covers

_R = Register
_L = CodeLabel
_LOC = SourceLocation(start_line=3, start_col=1, end_line=3, end_col=9)
_INT = te.scalar(TypeName("Int"))

_SAMPLES = (
    Const(result_reg=_R("%1"), value=Decimal("12.50"), type_expr=_INT, source_location=_LOC),
    LoadVar(result_reg=_R("%2"), name=VarName("x")),
    DeclVar(name=VarName("x"), value_reg=_R("%1")),
    StoreVar(name=VarName("x"), value_reg=_R("%1")),
    Symbolic(result_reg=_R("%3"), hint="param:args"),
    Binop(result_reg=_R("%4"), operator=BinopKind.NOT_IN, left=_R("%1"), right=_R("%2")),
    Unop(result_reg=_R("%5"), operator=UnopKind.NOT, operand=_R("%4")),
    CallFunction(result_reg=_R("%6"), func_name=FuncName("f"), args=(_R("%1"), SpreadArguments(register=_R("%2")))),
    CallMethod(result_reg=_R("%7"), obj_reg=_R("%1"), method_name=FuncName("m"), args=(_R("%2"),)),
    CallUnknown(result_reg=_R("%8"), target_reg=_R("%1"), args=()),
    CallCtorFunction(result_reg=_R("%9"), func_name=FuncName("C"), type_hint=_INT, args=(_R("%1"),)),
    CallWithMemory(result_reg=_R("%10"), location=VarName("__entry_X"), memory=_R("%1")),
    CallWithMemory(result_reg=_R("%11"), location=_R("%7"), memory=_R("%1")),
    LoadField(result_reg=_R("%12"), obj_reg=_R("%1"), field_name=FieldName("f", FieldKind.INDEX)),
    StoreField(obj_reg=_R("%1"), field_name=FieldName("f"), value_reg=_R("%2")),
    LoadFieldIndirect(result_reg=_R("%13"), obj_reg=_R("%1"), name_reg=_R("%2")),
    LoadIndex(result_reg=_R("%14"), arr_reg=_R("%1"), index_reg=_R("%2")),
    StoreIndex(arr_reg=_R("%1"), index_reg=_R("%2"), value_reg=SpreadArguments(register=_R("%3"))),
    LoadIndirect(result_reg=_R("%15"), ptr_reg=_R("%1")),
    StoreIndirect(ptr_reg=_R("%1"), value_reg=_R("%2")),
    ImportModule(module_path="a.b", resolved_path=PathName("a/b.py")),
    AddressOf(result_reg=_R("%16"), var_name=VarName("x")),
    NewObject(result_reg=_R("%17"), type_hint=te.ParameterizedType("Array", (_INT,))),
    NewArray(result_reg=_R("%18"), type_hint=_INT, size_reg=_R("%1")),
    Label_(label=_L("func_x_0")),
    Branch(label=_L("after_0")),
    BranchIf(cond_reg=_R("%1"), branch_targets=(_L("t"), _L("f"))),
    Return_(value_reg=_R("%1"), implicit=True),
    Return_(value_reg=None),
    Halt_(),
    Throw_(value_reg=_R("%1")),
    TryPush(catch_labels=(_L("c"),), finally_label=_L("fin"), end_label=NO_LABEL),
    TryPop(),
    AllocRegion(result_reg=_R("%19"), size_reg=_R("%1")),
    LoadRegion(result_reg=_R("%20"), region_reg=_R("%1"), offset_reg=_R("%2"), length=4),
    WriteRegion(region_reg=_R("%1"), offset_reg=_R("%2"), length=4, value_reg=_R("%3")),
    SetContinuation(name=ContinuationName("k"), target_label=_L("ret")),
    ResumeContinuation(name=ContinuationName("k")),
    Suspend(operand_reg=_R("%1")),
)

_TYPES = (
    te.UNKNOWN,
    _INT,
    te.EnumType("Colour"),
    te.AnnotationType("Final"),
    te.StructPatternType("Point"),
    te.ParameterizedType("Map", (_INT, te.UNKNOWN)),
    te.FunctionType((_INT,), te.UNKNOWN),
    te.UnionType(frozenset({_INT, te.EnumType("E")})),
    te.TypeVar("T", bound=_INT),
)


def _round_trip(value: object) -> object:
    codec = IrCodec()
    return codec.decode(json.loads(json.dumps(codec.encode(value))))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_samples_cover_every_instruction_class():
    assert {type(s) for s in _SAMPLES} == set(typing.get_args(Instruction))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("instruction", _SAMPLES, ids=lambda i: type(i).__name__)
def test_every_instruction_round_trips_with_its_field_types(instruction):
    decoded = _round_trip(instruction)
    assert (decoded, {f: type(getattr(decoded, f)) for f in vars(decoded)}) == (
        instruction,
        {f: type(getattr(instruction, f)) for f in vars(instruction)},
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("type_expr", _TYPES, ids=lambda t: type(t).__name__)
def test_every_type_expression_round_trips(type_expr):
    decoded = _round_trip(type_expr)
    assert (decoded, type(decoded)) == (type_expr, type(type_expr))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_null_objects_decode_to_their_singletons():
    decoded = _round_trip(LoadField())
    assert (
        type(decoded.result_reg),
        decoded.field_name is NO_FIELD_NAME,
        type(decoded.label),
        _round_trip(NO_VAR_NAME) is NO_VAR_NAME,
        _round_trip(NO_FUNC_NAME) is NO_FUNC_NAME,
        _round_trip(NO_CLASS_NAME) is NO_CLASS_NAME,
        _round_trip(NO_REGISTER) is NO_REGISTER,
    ) == (NoRegister, True, NoCodeLabel, True, True, True, True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "value",
    [Decimal("0.10"), [1, 2, 255], b"\x00\xc1", None, True, 7, 7.5, "PIC X", ["MAP1", "MAP2"]],
    ids=repr,
)
def test_const_values_keep_their_python_type(value):
    decoded = _round_trip(Const(result_reg=_R("%1"), value=value, type_expr=te.UNKNOWN))
    assert (decoded.value, type(decoded.value)) == (value, type(value))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_tables_round_trip():
    tables = (
        ExportTable(functions={FuncName("f"): _L("func_f_0")}, classes={ClassName("C"): _L("class_C_0")}, variables={VarName("v"): _R("%1")}),
        ImportRef(source_file=Path("a.py"), module_path="b", names=("x",), kind=ImportKind.USING, alias="y", line=4),
        FuncRef(name=FuncName("f"), label=_L("func_f_0")),
        ClassRef(name=ClassName("C"), label=_L("class_C_0"), parents=(ClassName("B"),)),
        SymbolTable(
            classes={ClassName("C"): ClassInfo(
                name=ClassName("C"),
                fields={FieldName("a"): FieldInfo(name=FieldName("a"), type_hint="Int", has_initializer=True, children=(FieldInfo(name=FieldName("b"), type_hint="", has_initializer=False),))},
                methods={FuncName("m"): FunctionInfo(name=FuncName("m"), params=("self",), return_type="")},
                constants={"K": "1"},
                parents=(),
            )},
            functions={},
            constants={"Z": "2"},
        ),
        {"WS-A": {"offset": 0, "length": 5, "category": "ALPHANUMERIC", "signed": False}},
    )
    assert [_round_trip(t) for t in tables] == list(tables)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_unknown_class_or_value_is_a_format_error():
    with pytest.raises(UnitFormatError, match="NoSuchInstruction"):
        IrCodec().decode({"$": "dc", "v": {"c": "NoSuchInstruction", "v": {}}})
    with pytest.raises(UnitFormatError, match="complex"):
        IrCodec().encode(1j)
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_ir_codec.py -q`
Expected: collection error — `ModuleNotFoundError: interpreter.project.ir_codec`.

- [ ] **Step 3: Implement**

`interpreter/project/unit_format_error.py`:

```python
"""A unit or linked-program file that does not decode."""


class UnitFormatError(Exception):
    """Raised for an unknown kind or class, an unencodable value, or a file of another format."""
```

`interpreter/project/ir_codec.py` — one class, small methods, table-driven dispatch (complexity ≤ 3 per function):

```python
"""Self-describing JSON for red-dragon IR values: instructions, type expressions, refs and tables."""

from __future__ import annotations

import dataclasses
import enum
import json
import typing
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path

from interpreter.class_name import NO_CLASS_NAME, ClassName, NoClassName
from interpreter.constants import Language
from interpreter.continuation_name import NO_CONTINUATION_NAME, ContinuationName, NoContinuationName
from interpreter.field_name import NO_FIELD_NAME, FieldKind, FieldName, NoFieldName
from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo, SymbolTable
from interpreter.func_name import NO_FUNC_NAME, FuncName, NoFuncName
from interpreter.instructions import Instruction
from interpreter.ir import NO_LABEL, CodeLabel, NoCodeLabel, SourceLocation, SpreadArguments
from interpreter.operator_kind import BinopKind, UnopKind
from interpreter.path_name import NO_PATH_NAME, NoPathName, PathName
from interpreter.project.types import ExportTable, ImportKind, ImportRef, ModuleUnit
from interpreter.project.unit_format_error import UnitFormatError
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import NO_REGISTER, NoRegister, Register
from interpreter.type_name import TypeName
from interpreter.types import type_expr as te
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.var_scope_info import VarScopeInfo
from interpreter.var_name import NO_VAR_NAME, NoVarName, VarName

_Wire = None | bool | int | float | str | list["_Wire"] | dict[str, "_Wire"]

_DATACLASSES = (
    *typing.get_args(Instruction),
    SpreadArguments, Register, CodeLabel, VarName, FieldName, FuncName, ContinuationName,
    PathName, ClassName, TypeName,
    te.ScalarType, te.EnumType, te.AnnotationType, te.StructPatternType,
    te.ParameterizedType, te.FunctionType, te.UnionType, te.TypeVar,
    FuncRef, ClassRef, ImportRef, ExportTable, ModuleUnit,
    FieldInfo, FunctionInfo, ClassInfo, SymbolTable, VarScopeInfo, TypeEnvironmentBuilder,
)
_SINGLETONS: Mapping[type, object] = {
    NoRegister: NO_REGISTER, NoCodeLabel: NO_LABEL, NoVarName: NO_VAR_NAME,
    NoFieldName: NO_FIELD_NAME, NoFuncName: NO_FUNC_NAME,
    NoContinuationName: NO_CONTINUATION_NAME, NoPathName: NO_PATH_NAME,
    NoClassName: NO_CLASS_NAME,
}
_ENUMS = (BinopKind, UnopKind, FieldKind, ImportKind, Language)


class IrCodec:
    """Encodes values to JSON-ready data and decodes them back to the same types."""

    def __init__(self) -> None:
        self._classes: Mapping[str, type] = {
            c.__name__: c for c in (*_DATACLASSES, *_SINGLETONS)
        }
        self._enums: Mapping[str, type[enum.Enum]] = {e.__name__: e for e in _ENUMS}
        self._encoders: tuple[tuple[type, Callable[[object], _Wire]], ...] = ...
```

The `...` above is not a placeholder to keep: the executor writes the encoder table as a tuple of `(type, method)` pairs in this order — `enum.Enum → _enum`, `(bool, int, float, str, NoneType) → identity`, `Decimal → _decimal`, `bytes → _bytes`, `Path → _path`, `tuple → _tuple`, `frozenset → _frozenset`, `list → _list`, `dict → _dict`, `SourceLocation → _loc`, `te.UnknownType → _unknown` — and `encode` is:

```python
    def encode(self, value: object) -> _Wire:
        encoder = next(
            (enc for kind, enc in self._encoders if isinstance(value, kind)),
            self._dataclass,
        )
        return encoder(value)

    def _dataclass(self, value: object) -> _Wire:
        match value:
            case _ if dataclasses.is_dataclass(value) and not isinstance(value, type):
                return self._tagged("dc", {
                    "c": type(value).__name__,
                    "v": {f.name: self.encode(getattr(value, f.name)) for f in dataclasses.fields(value)},
                })
            case _:
                raise UnitFormatError(f"no codec for {type(value).__name__}: {value!r}")

    def _tagged(self, kind: str, payload: _Wire) -> _Wire:
        return {"$": kind, "v": payload}
```

with the small encoders, each taking `object` and narrowing with `match` (`_enum` → `self._tagged("enum", {"c": type(v).__name__, "v": v.value})`; `_decimal` → `str(v)`; `_bytes` → `v.hex()`; `_path` → `str(v)`; `_tuple`/`_list` → list of `self.encode`; `_frozenset` → items in the order of their canonical JSON text (dumped with sorted object fields); `_dict` → list of `[self.encode(k), self.encode(v)]`; `_loc` → `[start_line, start_col, end_line, end_col]`; `_unknown` → `self._tagged("unknown_type", None)`).

`decode`:

```python
    def decode(self, wire: _Wire) -> object:
        match wire:
            case list():
                return [self.decode(item) for item in wire]
            case {"$": str(kind), "v": payload}:
                return self._decoder(kind)(payload)
            case _:
                return wire

    def _decoder(self, kind: str) -> Callable[[_Wire], object]:
        decoders: Mapping[str, Callable[[_Wire], object]] = {
            "enum": self._decode_enum, "decimal": lambda v: Decimal(str(v)),
            "bytes": lambda v: bytes.fromhex(str(v)), "path": lambda v: Path(str(v)),
            "tuple": lambda v: tuple(self._items(v)), "frozenset": lambda v: frozenset(self._items(v)),
            "dict": self._decode_dict, "loc": self._decode_loc,
            "unknown_type": lambda _v: te.UNKNOWN, "dc": self._decode_dataclass,
        }
        match decoders.get(kind):
            case None:
                raise UnitFormatError(f"unknown kind {kind!r}")
            case decoder:
                return decoder
```

`_decode_dataclass` looks the class up in `self._classes` (an unknown name raises `UnitFormatError` naming it), returns `_SINGLETONS[cls]` for a sentinel class, else `cls(**{name: self.decode(v) for name, v in fields})`. `_items(v)` decodes a list; `_decode_dict` builds `{self.decode(k): self.decode(val) for k, val in pairs}`; `_decode_enum` looks the enum up in `self._enums` and calls `cls(value)`; `_decode_loc` builds `SourceLocation(start_line=…, …)`. Payload shapes that do not match raise `UnitFormatError`.

If `_Wire`'s recursive alias does not type-check under red-dragon's pyright, write it as `type _Wire = None | bool | int | float | str | list[_Wire] | dict[str, _Wire]` (3.12+ syntax).

- [ ] **Step 4: Run the tests**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_ir_codec.py -q`
Expected: all succeed.

- [ ] **Step 5: Mutation checks**

(1) Drop `NoRegister` from `_SINGLETONS` → `test_null_objects_decode_to_their_singletons` fails (`Register("")` decodes, `type` differs). (2) Move the `enum.Enum` encoder after `str` → `Binop` and `Unop` samples fail (operator decodes as `str`). (3) Encode `Decimal` as `float(v)` → `test_const_values_keep_their_python_type[Decimal('0.10')]` fails. Restore after each.

- [ ] **Step 6: Gate and commit**

Run: `uv run --no-sync pyright interpreter/project/ir_codec.py interpreter/project/unit_format_error.py tests/unit/project/test_ir_codec.py` — 0 errors; `pre-commit run python-fp-lint --files interpreter/project/ir_codec.py interpreter/project/unit_format_error.py` — succeeds (ratchet unchanged).

```bash
git add interpreter/project/ir_codec.py interpreter/project/unit_format_error.py tests/unit/project/test_ir_codec.py
git commit -m "feat(project): IrCodec, self-describing JSON for IR values (red-dragon-ajps)"
```

---

### Task 2: `ModuleUnit` fields, `UnitCodec`, `LinkedCodec`

**Files:**
- Modify: `interpreter/project/types.py` (`ModuleUnit` gains two fields)
- Create: `interpreter/project/unit_codec.py`, `interpreter/project/linked_codec.py`
- Test: `tests/unit/project/test_unit_files.py`

**Interfaces:**
- Consumes: `IrCodec`, `UnitFormatError` (Task 1).
- Produces: `ModuleUnit.entry_label: CodeLabel = NO_LABEL`, `ModuleUnit.data_layout: dict[str, dict] = field(default_factory=dict)`; `UnitCodec(ir: IrCodec)` with `write(unit: ModuleUnit, path: Path) -> None`, `read(path: Path) -> ModuleUnit`; `LinkedCodec(ir: IrCodec)` with `write(linked: LinkedProgram, path: Path) -> None`, `read(path: Path) -> LinkedProgram`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/project/test_unit_files.py`:

```python
"""Unit and linked-program files round-trip; a bad file names itself."""

import pytest

from interpreter.frontend import make_cobol_parser
from interpreter.ir import CodeLabel
from interpreter.cfg import build_cfg
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.unit_codec import UnitCodec
from interpreter.project.unit_format_error import UnitFormatError
from tests.covers import NotLanguageFeature, covers

_SOURCE = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. CALLER.\n"
    b"       DATA DIVISION.\n"
    b"       WORKING-STORAGE SECTION.\n"
    b"       01 WS-N PIC 9(4) VALUE 5.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           ADD 1 TO WS-N.\n"
    b"           GOBACK.\n"
)


def _linked():
    _, linked = compile_cobol(_SOURCE, parser=make_cobol_parser())
    return linked


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_unit_round_trips_through_its_file(tmp_path):
    module = next(iter(_linked().modules.values()))
    unit = module.__class__(**{**vars(module), "entry_label": CodeLabel("func_caller_0"), "data_layout": {"WS-N": {"offset": 0, "length": 4}}})
    codec = UnitCodec(IrCodec())
    codec.write(unit, tmp_path / "caller.unit.json")
    assert codec.read(tmp_path / "caller.unit.json") == unit


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_program_round_trips_and_rebuilds_its_cfg(tmp_path):
    linked = _linked()
    codec = LinkedCodec(IrCodec())
    codec.write(linked, tmp_path / "caller.linked.json")
    read = codec.read(tmp_path / "caller.linked.json")
    assert (read, read.merged_cfg) == (linked, build_cfg(list(linked.merged_ir)))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("text", ['{"format": 99, "unit": null}', '{"format": 1, "un'])
def test_a_file_that_does_not_decode_names_itself(tmp_path, text):
    bad = tmp_path / "bad.unit.json"
    bad.write_text(text)
    with pytest.raises(UnitFormatError, match="bad.unit.json"):
        UnitCodec(IrCodec()).read(bad)
```

(`compile_cobol` still returns `(frontend, linked)` here; Task 4 changes it.)

- [ ] **Step 2: Run and see them fail**

Run: `. ~/code/red-dragon-forge/bridge-env.sh && uv run --no-sync python -m pytest tests/unit/project/test_unit_files.py -q`
Expected: collection error — no module `interpreter.project.unit_codec`.

- [ ] **Step 3: Implement**

`interpreter/project/types.py`, `ModuleUnit`: add after `symbol_table`

```python
    entry_label: CodeLabel = NO_LABEL
    data_layout: dict[str, dict] = field(default_factory=dict)
```

(import `NO_LABEL` from `interpreter.ir` if not already).

`interpreter/project/unit_codec.py`:

```python
"""A ModuleUnit to and from its .unit.json file."""

from __future__ import annotations

import json
from pathlib import Path

from interpreter.project.ir_codec import IrCodec
from interpreter.project.types import ModuleUnit
from interpreter.project.unit_format_error import UnitFormatError

_FORMAT = 1


class UnitCodec:
    def __init__(self, ir: IrCodec) -> None:
        self._ir = ir

    def write(self, unit: ModuleUnit, path: Path) -> None:
        path.write_text(json.dumps({"format": _FORMAT, "unit": self._ir.encode(unit)}), encoding="utf-8")

    def read(self, path: Path) -> ModuleUnit:
        try:
            return self._unit(json.loads(path.read_text(encoding="utf-8")))
        except (UnitFormatError, json.JSONDecodeError) as exc:
            raise UnitFormatError(f"{path}: {exc}") from exc

    def _unit(self, wire: object) -> ModuleUnit:
        match wire:
            case {"format": 1, "unit": body}:
                return self._module(self._ir.decode(body))
            case _:
                raise UnitFormatError(f"not a unit file of format {_FORMAT}")

    def _module(self, value: object) -> ModuleUnit:
        match value:
            case ModuleUnit():
                return value
            case _:
                raise UnitFormatError(f"expected a ModuleUnit, found {type(value).__name__}")
```

`interpreter/project/linked_codec.py` — same shape, format 1, body under `"linked"`; it encodes `{f.name: ir.encode(getattr(linked, f.name)) for f in dataclasses.fields(LinkedProgram) if f.name not in _DERIVED}` with `_DERIVED = frozenset({"merged_cfg", "merged_registry"})`, and reads by decoding each field, then

```python
        cfg = build_cfg(list(fields["merged_ir"]))
        registry = build_registry(
            list(fields["merged_ir"]), cfg,
            func_symbol_table=fields["func_symbol_table"],
            class_symbol_table=fields["class_symbol_table"],
        )
        return LinkedProgram(**fields, merged_cfg=cfg, merged_registry=registry)
```

(`merged_ir` decodes as a list, which is `LinkedProgram`'s declared type.)

- [ ] **Step 4: Run the tests**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_unit_files.py tests/unit/project -q`
Expected: all succeed. If `test_a_linked_program_round_trips…` fails only on `merged_registry` equality, compare `read.merged_registry` and `linked.merged_registry` field by field and fix the decode, not the assertion.

- [ ] **Step 5: Mutation check**

In `LinkedCodec.read`, build the registry without `func_symbol_table` → the round-trip test fails on `merged_registry.func_refs`. Restore.

- [ ] **Step 6: Commit**

```bash
git add interpreter/project/types.py interpreter/project/unit_codec.py interpreter/project/linked_codec.py tests/unit/project/test_unit_files.py
git commit -m "feat(project): unit and linked-program files (red-dragon-ajps)"
```

---

### Task 3: Extension strategies have a stable name

**Files:**
- Modify: `interpreter/frontend_extension_lowering.py`
- Modify (test fakes, add `name`): `tests/unit/project/test_cobol_compile.py` (`_FailsToLower`), `tests/unit/project/test_coprocessor_compile.py` (`_FakeStrategy`), `tests/unit/cobol/test_cobol_frontend_cache.py` (`_SpyStrategy`), `tests/unit/test_dialect_parser_seam.py` (`_ConformingStrategy`, `_SpyStrategy`, `_AlwaysHandles`, `_OrderSpy`; `_MissingHandles` stays non-conforming), `tests/integration/test_dialect_parser_seam.py` (`_SqlSpy`)

**Interfaces:**
- Produces: `RedDragonExtensionLoweringStrategy.name: str`.

- [ ] **Step 1: Failing test** — append to `tests/unit/test_dialect_parser_seam.py`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_strategy_without_a_name_does_not_conform():
    class _Nameless:
        def handles(self, stmt): return False
        def preprocess_program_dict(self, data): return data
        def on_procedure_entry(self, ctx, materialised): ...
        def lower(self, ctx, stmt, materialised): ...

    assert isinstance(_Nameless(), RedDragonExtensionLoweringStrategy) is False
```

- [ ] **Step 2: Run** — `uv run --no-sync python -m pytest tests/unit/test_dialect_parser_seam.py -q -k nameless_or_without_a_name` — Expected: FAIL (`True is False`).

- [ ] **Step 3: Implement** — in the protocol, before `handles`:

```python
    name: str
    """A stable name for this extension (``"cics"``, ``"sql"``): part of the
    digest that names a program's compiled files."""
```

and give every listed test fake a class attribute `name = "<fake name>"` (e.g. `name = "fails-to-lower"`).

- [ ] **Step 4: Run** — `uv run --no-sync python -m pytest tests/unit/test_dialect_parser_seam.py tests/unit/project tests/unit/cobol/test_cobol_frontend_cache.py tests/integration/test_dialect_parser_seam.py -q` — Expected: all succeed.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontend_extension_lowering.py tests/unit/test_dialect_parser_seam.py tests/unit/project/test_cobol_compile.py tests/unit/project/test_coprocessor_compile.py tests/unit/cobol/test_cobol_frontend_cache.py tests/integration/test_dialect_parser_seam.py
git commit -m "feat(frontend): extension lowering strategies carry a stable name (red-dragon-ajps)"
```

---

### Task 4: The three stages; `compile_cobol` returns the linked program read from disk

**Files:**
- Create: `interpreter/project/lowering_settings.py`
- Modify: `interpreter/project/cobol_compile.py` (stages; `compile_cobol_module` returns a `ModuleUnit`; `parallel_parse_to_cache` removed)
- Modify: `interpreter/project/coprocessor_compile.py` (returns `LinkedProgram`)
- Modify callers: `interpreter/run.py:1235`, `interpreter/__main__.py:82`; tests listed in Step 5
- Modify: `docs/architectural-design-decisions.md` (ADR-183), and any living doc that shows `compile_cobol`/`compile_program` returning a tuple (`rg -n "compile_cobol|compile_program" docs README.md -g '!docs/superpowers/**' -g '!docs/records/**'`)
- Test: `tests/unit/project/test_cobol_compile.py`

**Interfaces:**
- Consumes: `UnitCodec`, `LinkedCodec`, `IrCodec` (Tasks 1–2); strategy `name` (Task 3).
- Produces: `LoweringSettings(lp: LP, extension_names: tuple[str, ...], tolerant: bool, copybook_dirs: tuple[Path, ...])` with `artifact(program: SourceFile, work_dir: Path, kind: str) -> Path`; `parse_stage(programs: Sequence[SourceFile], parser, settings: LoweringSettings, work_dir: Path) -> Mapping[Path, Path]`; `link_stage(main_unit: Path, units: Sequence[Path], work_dir: Path) -> Path`; `compile_cobol(...) -> LinkedProgram` (parameter `ast_cache_dir` renamed `work_dir`); `compile_program(...) -> LinkedProgram`.

- [ ] **Step 1: Failing tests** — append to `tests/unit/project/test_cobol_compile.py` (and change its existing `_, linked = compile_cobol(...)` lines to `linked = compile_cobol(...)`; the `compile_cobol_module` test at ~line 64 reads `module.data_layout` and `module.entry_label` instead of the frontend's):

```python
class _CountingParser:
    """The real parser, recording every program it is asked to parse."""

    def __init__(self, inner, parsed: list[str]) -> None:
        self._inner, self.parsed = inner, parsed

    def with_addressing_mode(self, mode):
        return _CountingParser(self._inner.with_addressing_mode(mode), self.parsed)

    def parse_to_file(self, source: bytes, out):
        self.parsed.append(out.name)
        return self._inner.parse_to_file(source, out)


_CALLEE = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. CALLEE.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           GOBACK.\n"
)
_CALLER = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. CALLER.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           CALL 'CALLEE'.\n"
    b"           GOBACK.\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_second_compile_in_the_same_work_directory_reuses_every_file(tmp_path):
    parsed: list[str] = []
    parser = _CountingParser(make_cobol_parser(), parsed)
    programs = (SourceFile(Path("CALLEE.cbl"), _CALLEE),)
    first = compile_cobol(_CALLER, parser=parser, programs=programs, work_dir=tmp_path)
    files = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    second = compile_cobol(_CALLER, parser=parser, programs=programs, work_dir=tmp_path)
    assert (
        len(parsed),
        sorted(p.name.split(".", 1)[1] for p in tmp_path.iterdir()),
        {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == files,
        second.entry_func_label,
        second.merged_ir == first.merged_ir,
    ) == (2, ["ast.json", "ast.json", "linked.json", "unit.json", "unit.json"], True, CodeLabel("__main__.func_caller_0"), True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_edited_source_or_new_settings_gets_new_files(tmp_path):
    compile_cobol(_CALLER, parser=make_cobol_parser(), work_dir=tmp_path)
    edited = _CALLER.replace(b"GOBACK", b"STOP RUN")
    compile_cobol(edited, parser=make_cobol_parser(), work_dir=tmp_path)
    compile_cobol(_CALLER, parser=make_cobol_parser(), work_dir=tmp_path, tolerant=True)
    assert len(list(tmp_path.glob("__main__-*.unit.json"))) == 3


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_callee_that_fails_to_lower_has_no_unit_and_a_rerun_still_links(tmp_path, caplog):
    programs = (SourceFile(Path("CALLEE.cbl"), _CALLEE),)
    strategies = [_FailsToLower("CALLEE")]
    compile_cobol(_CALLER, parser=make_cobol_parser(), programs=programs, extension_strategies=strategies, work_dir=tmp_path)
    linked = compile_cobol(_CALLER, parser=make_cobol_parser(), programs=programs, extension_strategies=strategies, work_dir=tmp_path)
    assert (
        sorted(p.name.split("-")[0] for p in tmp_path.glob("*.unit.json")),
        sorted(str(path) for path in linked.modules),
    ) == (["__main__"], ["__main__.cbl", "__start_up__"])
```

(`_FailsToLower`'s constructor arguments are whatever the existing class takes — match them. If `linked.modules` holds paths other than these two, the assertion's second element is the set the reachability filter keeps; assert the exact set it produces with only the main program present.)

Cross-process test — `tests/integration/test_linked_file_cross_process.py`:

```python
"""A linked file written by one process runs in a fresh one."""

import subprocess
import sys
from pathlib import Path

from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from tests.covers import NotLanguageFeature, covers

_PROGRAM = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. ADDER.\n"
    b"       DATA DIVISION.\n"
    b"       WORKING-STORAGE SECTION.\n"
    b"       01 WS-N PIC 9(4) VALUE 5.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           ADD 37 TO WS-N.\n"
    b"           DISPLAY WS-N.\n"
    b"           GOBACK.\n"
)

_RUNNER = """
import sys
from pathlib import Path
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked
linked = LinkedCodec(IrCodec()).read(Path(sys.argv[1]))
run_linked(linked, EntryPoint.function(lambda ref: ref.label == linked.entry_func_label), initial_vm=initial_vm_state())
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_file_runs_in_a_fresh_process(tmp_path):
    compile_cobol(_PROGRAM, parser=make_cobol_parser(), work_dir=tmp_path)
    (linked_file,) = tmp_path.glob("*.linked.json")
    runner = tmp_path / "runner.py"
    runner.write_text(_RUNNER)
    result = subprocess.run([sys.executable, str(runner), str(linked_file)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "0042"
```

(If DISPLAY output reaches stdout through a different io provider in `initial_vm_state()`, read `WS-N` back from the VM instead and print it from the runner; the assertion stays `"0042"`.)

- [ ] **Step 2: Run and see them fail**

Run: `. ~/code/red-dragon-forge/bridge-env.sh && uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py tests/integration/test_linked_file_cross_process.py -q`
Expected: FAIL — `TypeError` from `compile_cobol` rejecting the new `work_dir` argument.

- [ ] **Step 3: Implement**

`interpreter/project/lowering_settings.py`:

```python
"""What a COBOL program's compiled files depend on besides its source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cobol_asg.lp import LP
from interpreter.project.source_file import SourceFile


@dataclass(frozen=True)
class LoweringSettings:
    lp: LP
    extension_names: tuple[str, ...]
    tolerant: bool
    copybook_dirs: tuple[Path, ...]

    def artifact(self, program: SourceFile, work_dir: Path, kind: str) -> Path:
        return work_dir / f"{program.path.stem}-{self._digest(program.source)}.{kind}.json"

    def _digest(self, source: bytes) -> str:
        settings = json.dumps(
            [self.lp.value, list(self.extension_names), self.tolerant, [str(d) for d in self.copybook_dirs]]
        )
        return hashlib.sha256(source + b"\0" + settings.encode("utf-8")).hexdigest()
```

`interpreter/project/cobol_compile.py`:

- `compile_cobol_module(...)` returns `ModuleUnit` (not a tuple), with `entry_label=CodeLabel(f"func_{frontend.program_id.lower()}_0")` and `data_layout=frontend.data_layout` set on the unit.
- `parse_stage(programs, parser, settings, work_dir)`: `targets = {p.path: settings.artifact(p, work_dir, "ast") for p in programs}`; parse only `p` with `not targets[p.path].exists()`, in a `ThreadPoolExecutor` with a tqdm bar (as `AstStore.parse_all` does), calling `parser.parse_to_file(p.source, targets[p.path])` and wrapping any failure as `AstParseError(f"{p.path.name}: {type(exc).__name__}: {exc}")`; return `targets`. `work_dir.mkdir(parents=True, exist_ok=True)` first.
- `_Lowering` gains `settings: LoweringSettings` and `units: UnitCodec`; `lower(program, ast_file, work_dir) -> Path` writes the unit to `settings.artifact(program, work_dir, "unit")` unless it exists and returns that path; `lower_or_skip(program, ast_file, work_dir) -> tuple[Path, ...]` returns `()` with today's warning on failure.
- `link_stage(main_unit, units, work_dir)`:

```python
def link_stage(main_unit: Path, units: Sequence[Path], work_dir: Path) -> Path:
    stem = main_unit.name.removesuffix(".unit.json").rpartition("-")[0]
    digest = hashlib.sha256("\0".join(p.name for p in (main_unit, *units)).encode("utf-8")).hexdigest()
    target = work_dir / f"{stem}-{digest}.linked.json"
    if not target.exists():
        LinkedCodec(IrCodec()).write(_link(main_unit, units), target)
    return target


def _link(main_unit: Path, units: Sequence[Path]) -> LinkedProgram:
    codec = UnitCodec(IrCodec())
    main = codec.read(main_unit)
    modules = {main.path: main, **{u.path: u for u in map(codec.read, units)}}
    graph = {path: [] for path in modules} | {main.path: [p for p in modules if p != main.path]}
    linked_modules, linked_graph = with_start_up(run_unit_allocation(), Language.COBOL, modules, graph)
    linked = link_modules(
        modules=linked_modules, import_graph=linked_graph, project_root=Path("/"),
        topo_order=topological_sort(linked_graph), language=Language.COBOL,
        type_env_builder=TypeEnvironmentBuilder(), data_layout=main.data_layout,
    )
    return dataclasses.replace(
        linked,
        entry_func_label=main.entry_label.namespace(module_prefix(main.path, Path("/"))),
        ast_paths={u.path: f.with_name(f.name.replace(".unit.json", ".ast.json")) for u, f in ((codec.read(f), f) for f in (main_unit, *units))},
    )
```

(`run_unit_allocation` from `interpreter.cobol.run_unit`; `module_prefix` from `interpreter.project.linker`. Read each unit file once — fold the `ast_paths` comprehension onto the already-read units rather than re-reading, if the lint ratchet or a reviewer prefers.)

- `compile_cobol(...)` → `LinkedProgram`:

```python
    settings = LoweringSettings(lp, tuple(s.name for s in extension_strategies), tolerant, tuple(copybook_dirs))
    work = _cache_dir(work_dir)
    main = SourceFile(Path("__main__.cbl"), source)
    programs_by_path = {p.path: p for p in (main, *programs)}
    asts = parse_stage(tuple(programs_by_path.values()), mode_parser, settings, work)
    lowering = _Lowering(..., settings=settings, units=UnitCodec(IrCodec()))
    main_unit = lowering.lower(main, asts[main.path], work)
    callees = tuple(
        unit for path, program in programs_by_path.items() if path != main.path
        for unit in lowering.lower_or_skip(program, asts[path], work)
    )
    return LinkedCodec(IrCodec()).read(link_stage(main_unit, callees, work))
```

Delete `parallel_parse_to_cache`; its tests (`test_cobol_compile.py` ~126–152) become `parse_stage` tests asserting the same file set under the new names.

`interpreter/project/coprocessor_compile.py`: `compile_program` returns `LinkedProgram`; docstring updated.

- [ ] **Step 4: Run the new tests**

Run: `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py tests/integration/test_linked_file_cross_process.py tests/unit/project/test_unit_files.py -q`
Expected: all succeed (update `test_unit_files.py`'s `_linked()` to `return compile_cobol(...)`).

- [ ] **Step 5: Callers**

`interpreter/run.py:1235` → `linked = compile_cobol(...)`; `interpreter/__main__.py:82` → `linked = compile_program(...)`; every test listed under item 8 of the plan's research (`tests/unit/test_lower_program_init.py:171`, `tests/unit/project/test_cobol_compile.py`, `tests/unit/project/test_coprocessor_compile.py`, `tests/unit/cobol/test_arithmetic_decimal_precision.py:78`, `tests/integration/cobol_helpers.py:93,204`, `tests/integration/test_cobol_exact_arithmetic.py:246`): `_, linked = …` → `linked = …`. Find any missed site with `rg -n "_, linked = compile_|frontend, linked = compile_" interpreter tests scripts`.

- [ ] **Step 6: Full suite**

Run: `uv run --no-sync python -m pytest tests -q -n auto --ignore=tests/external > /tmp/ajps.log 2>&1; tail -3 /tmp/ajps.log`
Expected: no failures.

- [ ] **Step 7: Mutation checks**

(1) In `parse_stage`, parse every program regardless of existing files → `test_a_second_compile…` fails (`len(parsed)` 4). (2) Drop `tolerant` from `LoweringSettings._digest` → `test_an_edited_source_or_new_settings_gets_new_files` fails (2 files). (3) In `link_stage`, set `entry_func_label` from `main.entry_label` without the namespace → the reuse test fails on `entry_func_label`. Restore after each.

- [ ] **Step 8: Docs**

ADR-183 in `docs/architectural-design-decisions.md`:

```markdown
### ADR-183: COBOL compiles in three stages chained through files (2026-10-13)

**Context:** `compile_cobol` parsed, lowered and linked in one call, handing a live frontend and in-memory `ModuleUnit`s from stage to stage, so nothing compiled could be reused by another process (red-dragon-ajps).

**Decision:** Parse writes `<stem>-<digest>.ast.json`, lower writes `.unit.json`, link writes `.linked.json`, and `compile_cobol` returns the `LinkedProgram` read back from the linked file. The digest covers the source bytes and the lowering settings; a stage skips a program whose output exists. `IrCodec` encodes values as self-describing JSON; `UnitCodec` and `LinkedCodec` own the two formats. The linked file holds every field but the CFG and registry, which are rebuilt on read. Extension strategies carry a stable `name`.

**Consequences:** `compile_cobol` and `compile_program` return the `LinkedProgram` alone. A caller that keeps its work directory reuses every stage's output; staleness beyond source and settings (copybooks, lowering version) is the caller's to handle by deleting the directory.
```

Update any living doc found in the Files list's `rg`.

- [ ] **Step 9: Commit and push red-dragon**

```bash
git add -A interpreter tests docs
git commit -m "feat(project): COBOL compiles in three stages chained through files (red-dragon-ajps)"
git push origin main
```

---

### Task 5: Forge — names, callers, gate

Runs in `~/code/red-dragon-forge` after Task 4 is pushed.

**Files:**
- Modify: `vendor/red-dragon` (bump)
- Modify: `cicada/cics/strategy.py` (`CicsLoweringStrategy.name = "cics"`), `squall/squall/strategy.py` (`SqlLoweringStrategy.name = "sql"`), `cicada/tests/integration/cics/test_tn3270_region.py` (`_NoOpStrategy.name`)
- Modify callers: `cobol_harness/vsam.py:72`, `cicada/cics/bootstrap.py:69`, `cicada/cics/tn3270/region.py:119`, `jackal/jackal/program_compiler.py:48`, `docs/presentation/capture/db2_inqcust_capture.py:273,282,467`, `tests/integration/test_inqcust_e2e.py:233,247` (`wrapper_frontend.data_layout` → `wrapper_linked.data_layout`), `tests/integration/test_cics_sql_composition.py:58,123`, `tests/integration/test_cics_adapter.py:77,110`, `tests/integration/test_carddemo_db2_abend_rollback.py:118`, `tests/integration/test_sql_adapter.py:67`, `tests/integration/test_carddemo_db2_compile.py:119,127,149,172`, `tests/integration/test_harness_state.py:23`, `cicada/tests/integration/cics/test_ceedays_stub.py:62`, `squall/tests/integration/squall_cobol_helpers.py:68,92,114`, `squall/tests/unit/test_whenever.py:132`, `squall/tests/integration/test_cross_process_run.py:31`

- [ ] **Step 1: Bump and update**

```bash
cd ~/code/red-dragon-forge/vendor/red-dragon && git fetch -q origin && git checkout -q origin/main && cd ../..
```

Add the two `name` class attributes and the test fake's; change every listed call site from `(frontend, linked)` / `[1]` to the single `LinkedProgram`. `squall_cobol_helpers.compile_cobol` returns `LinkedProgram`; its callers follow.

- [ ] **Step 2: Confirm no tuple unpacking remains**

Run: `rg -n "compile_program\(|compile_cobol\(" cicada squall jackal red_dragon_forge cobol_harness tests docs/presentation -g '*.py' | rg "_, |, linked|\[1\]"`
Expected: no output.

- [ ] **Step 3: Gate**

Run: `make fmt && uv run pyright | tail -1 && uv run lint-imports | tail -1 && pre-commit run python-fp-lint-check --hook-stage manual --all-files | tail -1`, then `docker inspect -f '{{.State.Health.Status}}' squall-db2` (restart if unhealthy) and `. ./bridge-env.sh && make test-all > /tmp/ajps-forge.log 2>&1; grep -E "^=+ .* in [0-9.]+s" /tmp/ajps-forge.log`
Expected: pyright errors unchanged (32, all cobble); every suite succeeds.

- [ ] **Step 4: c3270 CardDemo**

Copy `docs/presentation/capture/carddemo_3270_video.sh` to the scratchpad with `ROOT` set to the forge root and `OUT` to a scratchpad directory, run it, build the 12-frame sheet (`ffmpeg -loglevel error -y -i <out>/carddemo-3270.mp4 -vf "fps=12/<duration>,scale=640:-1,tile=3x4" -frames:v 1 <out>/sheet.png`) and compare with the 2026-10-13 baseline frames (sign-on, menu, account update "Changes validated", account view, user list, USER0006 added / updated to CAROLINE / deleted).

- [ ] **Step 5: Commit, push, beads**

```bash
git add -A vendor/red-dragon cicada squall jackal cobol_harness tests docs/presentation
git commit -m "chore(vendor): bump red-dragon; compile_program returns the linked program read from disk"
git push origin main
```

In `~/code/red-dragon`: `bd close red-dragon-ajps --reason "ADR-183: parse, lower and link chained through files; compile_cobol returns the LinkedProgram read from disk."`, `bd export -o issues/issues.jsonl`, commit, push. In the forge, file a bead: "cicada region start and jackal keep a persistent COBOL work directory (reuse compiled units across runs)", referencing red-dragon-ajps; `bd export -o issues/issues.jsonl`, commit, push.
