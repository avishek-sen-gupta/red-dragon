"""Per-opcode typed instruction classes.

Each IR opcode has a frozen dataclass with named, typed fields replacing
the old flat ``operands: list[Any]`` representation.

The ``IRInstruction()`` factory function in ``ir.py`` uses the private
``_to_typed()`` converter to build typed instructions from flat
(opcode, operands) arguments.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
    Any,
    Self,
    Union,  # noqa: F401 — Union used in Instruction type alias
    get_args,
    get_origin,
    get_type_hints,
)

from interpreter.ir import (
    CodeLabel,
    NO_LABEL,
    NO_SOURCE_LOCATION,
    Opcode,
    SourceLocation,
    SpreadArguments,
)
from interpreter.operator_kind import BinopKind, UnopKind, resolve_binop, resolve_unop
from interpreter.register import NO_REGISTER, Register
from interpreter.types.type_expr import UNKNOWN, TypeExpr, scalar
from interpreter.field_name import FieldName, FieldKind, NO_FIELD_NAME
from interpreter.func_name import FuncName, NO_FUNC_NAME
from interpreter.var_name import NO_VAR_NAME, VarName


def _is_union(origin: object) -> bool:
    """Check if origin is a union type (typing.Union or types.UnionType for X | Y syntax)."""
    return origin is Union or origin is types.UnionType


def _is_optional_register(hint: object) -> bool:
    """Check if hint is Register | None."""
    origin = get_origin(hint)
    if _is_union(origin):
        args = get_args(hint)
        return Register in args and type(None) in args
    return False


def _is_register_args_tuple(hint: object) -> bool:
    """Check if hint is tuple[Register | SpreadArguments, ...]."""
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            inner = args[0]
            inner_origin = get_origin(inner)
            if _is_union(inner_origin):
                inner_args = get_args(inner)
                return Register in inner_args and SpreadArguments in inner_args
    return False


def _is_label_tuple(hint: object) -> bool:
    """Check if hint is tuple[CodeLabel, ...]."""
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        return len(args) == 2 and args[0] is CodeLabel and args[1] is Ellipsis
    return False


def _as_register(val: Any) -> Register | Any:
    """Wrap a value as Register if it looks like a register reference (%…).

    Still needed for ``to_typed()`` conversions on flat IRInstructions
    produced by ``EmitContext.inline_ir()`` and test helpers.  Only strings
    that begin with '%' are register refs; literals are kept as-is.
    """
    if isinstance(val, Register):
        return val
    if isinstance(val, str) and val.startswith("%"):
        return Register(val)
    return val  # literal — keep as-is


# ── Base ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InstructionBase:
    """Shared metadata carried by every instruction."""

    source_location: SourceLocation = field(default_factory=lambda: NO_SOURCE_LOCATION)

    def map_registers(self, fn: Callable[[Register], Register]) -> Self:
        """Apply fn to every Register-typed field, return a new instruction.

        Handles string values in Register-typed fields by wrapping them as
        Register before applying fn (legacy compatibility for construction
        sites that still pass strings instead of Register objects).
        """
        changes: dict[str, object] = {}
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            hint = hints.get(f.name, f.type)
            val = getattr(self, f.name)
            if isinstance(val, Register):
                changes[f.name] = fn(val)
            elif (
                isinstance(val, str)
                and val.startswith("%")
                and (hint is Register or _is_optional_register(hint))
            ):
                changes[f.name] = fn(Register(val))
            elif isinstance(val, SpreadArguments):
                changes[f.name] = SpreadArguments(register=fn(val.register))
            elif val is None and _is_optional_register(hint):
                pass  # None stays None
            elif isinstance(val, tuple) and _is_register_args_tuple(hint):
                changes[f.name] = tuple(
                    (
                        SpreadArguments(register=fn(a.register))
                        if isinstance(a, SpreadArguments)
                        else (
                            fn(Register(a))
                            if isinstance(a, str) and a.startswith("%")
                            else fn(a) if isinstance(a, Register) else a
                        )  # literal (str/int/float) — keep as-is
                    )
                    for a in val
                )
        return dataclasses.replace(self, **changes) if changes else self

    def map_labels(self, fn: Callable[[CodeLabel], CodeLabel]) -> Self:
        """Apply fn to every CodeLabel-typed field, return a new instruction."""
        changes: dict[str, object] = {}
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            hint = hints.get(f.name, f.type)
            val = getattr(self, f.name)
            if isinstance(val, CodeLabel):
                changes[f.name] = fn(val)
            elif isinstance(val, tuple) and _is_label_tuple(hint):
                changes[f.name] = tuple(fn(lbl) for lbl in val)
        return dataclasses.replace(self, **changes) if changes else self

    def __str__(self) -> str:
        """Render in the same format as IRInstruction.__str__."""
        parts: list[str] = []
        if (
            hasattr(self, "label")
            and self.label.is_present()
            and self.opcode == Opcode.LABEL
        ):
            base = f"{self.label}:"
        else:
            if self.result_reg.is_present():
                parts.append(f"{self.result_reg} =")
            parts.append(self.opcode.value.lower())
            for op in self.operands:
                parts.append(str(op))
            if hasattr(self, "branch_targets") and self.branch_targets:
                parts.append(",".join(str(t) for t in self.branch_targets))
            elif (
                hasattr(self, "label")
                and self.label.is_present()
                and self.opcode != Opcode.LABEL
            ):
                parts.append(str(self.label))
            base = " ".join(parts)
        if not self.source_location.is_unknown():
            return f"{base}  # {self.source_location}"
        return base


# ── Variables & Constants ────────────────────────────────────────


@dataclass(frozen=True)
class Const(InstructionBase):
    """CONST: load a literal value into a register."""

    result_reg: Register = NO_REGISTER
    value: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CONST

    @property
    def operands(self) -> list[Any]:
        return [self.value] if self.value != "" else []


@dataclass(frozen=True)
class LoadVar(InstructionBase):
    """LOAD_VAR: load a named variable into a register."""

    result_reg: Register = NO_REGISTER
    name: VarName = NO_VAR_NAME

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_VAR

    @property
    def operands(self) -> list[Any]:
        return [str(self.name)]


@dataclass(frozen=True)
class DeclVar(InstructionBase):
    """DECL_VAR: declare a variable and assign a value from a register."""

    name: VarName = NO_VAR_NAME
    value_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.DECL_VAR

    @property
    def operands(self) -> list[Any]:
        return [str(self.name), str(self.value_reg)]


@dataclass(frozen=True)
class StoreVar(InstructionBase):
    """STORE_VAR: assign to an existing variable from a register."""

    name: VarName = NO_VAR_NAME
    value_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.STORE_VAR

    @property
    def operands(self) -> list[Any]:
        return [str(self.name), str(self.value_reg)]


@dataclass(frozen=True)
class Symbolic(InstructionBase):
    """SYMBOLIC: parameter placeholder or unknown value."""

    result_reg: Register = NO_REGISTER
    hint: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.SYMBOLIC

    @property
    def operands(self) -> list[Any]:
        return [self.hint] if self.hint else []


# ── Arithmetic ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Binop(InstructionBase):
    """BINOP: binary operation (operator, left register, right register)."""

    result_reg: Register = NO_REGISTER
    operator: BinopKind = BinopKind.ADD
    left: Register = NO_REGISTER
    right: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.BINOP

    @property
    def operands(self) -> list[Any]:
        return [
            getattr(self.operator, "value", self.operator),
            str(self.left) if isinstance(self.left, Register) else self.left,
            str(self.right) if isinstance(self.right, Register) else self.right,
        ]


@dataclass(frozen=True)
class Unop(InstructionBase):
    """UNOP: unary operation (operator, operand register)."""

    result_reg: Register = NO_REGISTER
    operator: UnopKind = UnopKind.NEG
    operand: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.UNOP

    @property
    def operands(self) -> list[Any]:
        return [getattr(self.operator, "value", self.operator), str(self.operand)]


# ── Calls ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CallFunction(InstructionBase):
    """CALL_FUNCTION: call a named function with arguments."""

    result_reg: Register = NO_REGISTER
    func_name: FuncName = NO_FUNC_NAME
    args: tuple[Register | SpreadArguments, ...] = ()

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_FUNCTION

    @property
    def operands(self) -> list[Any]:
        return [
            str(self.func_name),
            *(str(a) if isinstance(a, Register) else a for a in self.args),
        ]


@dataclass(frozen=True)
class CallMethod(InstructionBase):
    """CALL_METHOD: call a method on an object."""

    result_reg: Register = NO_REGISTER
    obj_reg: Register = NO_REGISTER
    method_name: FuncName = NO_FUNC_NAME
    args: tuple[Register | SpreadArguments, ...] = ()

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_METHOD

    @property
    def operands(self) -> list[Any]:
        return [
            str(self.obj_reg),
            str(self.method_name),
            *(str(a) if isinstance(a, Register) else a for a in self.args),
        ]


@dataclass(frozen=True)
class CallUnknown(InstructionBase):
    """CALL_UNKNOWN: call a dynamic target (register holds callable)."""

    result_reg: Register = NO_REGISTER
    target_reg: Register = NO_REGISTER
    args: tuple[Register | SpreadArguments, ...] = ()

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_UNKNOWN

    @property
    def operands(self) -> list[Any]:
        return [
            str(self.target_reg),
            *(str(a) if isinstance(a, Register) else a for a in self.args),
        ]


@dataclass(frozen=True)
class CallCtorFunction(InstructionBase):
    """CALL_CTOR: call a class constructor with typed type hint."""

    result_reg: Register = NO_REGISTER
    func_name: FuncName = NO_FUNC_NAME
    type_hint: TypeExpr = UNKNOWN
    args: tuple[Register | SpreadArguments, ...] = ()

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.CALL_CTOR

    @property
    def operands(self) -> list[Any]:
        return [
            str(self.func_name),
            *(str(a) if isinstance(a, Register) else a for a in self.args),
        ]


# ── Memory — Fields ──────────────────────────────────────────────


@dataclass(frozen=True)
class LoadField(InstructionBase):
    """LOAD_FIELD: load a named field from an object."""

    result_reg: Register = NO_REGISTER
    obj_reg: Register = NO_REGISTER
    field_name: FieldName = NO_FIELD_NAME

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_FIELD

    @property
    def operands(self) -> list[Any]:
        return [str(self.obj_reg), str(self.field_name)]


@dataclass(frozen=True)
class StoreField(InstructionBase):
    """STORE_FIELD: store a value into a named field on an object."""

    obj_reg: Register = NO_REGISTER
    field_name: FieldName = NO_FIELD_NAME
    value_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.STORE_FIELD

    @property
    def operands(self) -> list[Any]:
        return [str(self.obj_reg), str(self.field_name), str(self.value_reg)]


@dataclass(frozen=True)
class LoadFieldIndirect(InstructionBase):
    """LOAD_FIELD_INDIRECT: load a field whose name is in a register."""

    result_reg: Register = NO_REGISTER
    obj_reg: Register = NO_REGISTER
    name_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_FIELD_INDIRECT

    @property
    def operands(self) -> list[Any]:
        return [str(self.obj_reg), str(self.name_reg)]


# ── Memory — Indexing ────────────────────────────────────────────


@dataclass(frozen=True)
class LoadIndex(InstructionBase):
    """LOAD_INDEX: load from an array/dict by index/key register."""

    result_reg: Register = NO_REGISTER
    arr_reg: Register = NO_REGISTER
    index_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_INDEX

    @property
    def operands(self) -> list[Any]:
        return [str(self.arr_reg), str(self.index_reg)]


@dataclass(frozen=True)
class StoreIndex(InstructionBase):
    """STORE_INDEX: store into an array/dict at index/key register."""

    arr_reg: Register = NO_REGISTER
    index_reg: Register = NO_REGISTER
    value_reg: Register | SpreadArguments = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.STORE_INDEX

    @property
    def operands(self) -> list[Any]:
        vr = (
            self.value_reg
            if isinstance(self.value_reg, SpreadArguments)
            else str(self.value_reg)
        )
        return [str(self.arr_reg), str(self.index_reg), vr]


# ── Memory — Pointers ────────────────────────────────────────────


@dataclass(frozen=True)
class LoadIndirect(InstructionBase):
    """LOAD_INDIRECT: dereference a pointer register."""

    result_reg: Register = NO_REGISTER
    ptr_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_INDIRECT

    @property
    def operands(self) -> list[Any]:
        return [str(self.ptr_reg)]


@dataclass(frozen=True)
class StoreIndirect(InstructionBase):
    """STORE_INDIRECT: write through a pointer register."""

    ptr_reg: Register = NO_REGISTER
    value_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.STORE_INDIRECT

    @property
    def operands(self) -> list[Any]:
        return [str(self.ptr_reg), str(self.value_reg)]


@dataclass(frozen=True)
class AddressOf(InstructionBase):
    """ADDRESS_OF: take address of a named variable."""

    result_reg: Register = NO_REGISTER
    var_name: VarName = NO_VAR_NAME

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.ADDRESS_OF

    @property
    def operands(self) -> list[Any]:
        return [str(self.var_name)]


# ── Objects ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewObject(InstructionBase):
    """NEW_OBJECT: allocate a new object on the heap."""

    result_reg: Register = NO_REGISTER
    type_hint: TypeExpr = UNKNOWN

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.NEW_OBJECT

    @property
    def operands(self) -> list[Any]:
        return [str(self.type_hint)] if self.type_hint else []


@dataclass(frozen=True)
class NewArray(InstructionBase):
    """NEW_ARRAY: allocate a new array/list/dict on the heap."""

    result_reg: Register = NO_REGISTER
    type_hint: TypeExpr = UNKNOWN
    size_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.NEW_ARRAY

    @property
    def operands(self) -> list[Any]:
        return [str(self.type_hint), str(self.size_reg)]


# ── Control Flow ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Label_(InstructionBase):
    """LABEL: block entry point (pseudo-instruction)."""

    label: CodeLabel = NO_LABEL

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LABEL

    @property
    def operands(self) -> list[Any]:
        return []


@dataclass(frozen=True)
class Branch(InstructionBase):
    """BRANCH: unconditional jump to a label."""

    label: CodeLabel = NO_LABEL

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.BRANCH

    @property
    def operands(self) -> list[Any]:
        return []


@dataclass(frozen=True)
class BranchIf(InstructionBase):
    """BRANCH_IF: conditional branch on a register value."""

    cond_reg: Register = NO_REGISTER
    branch_targets: tuple[CodeLabel, ...] = ()

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL

    @property
    def opcode(self) -> Opcode:
        return Opcode.BRANCH_IF

    @property
    def operands(self) -> list[Any]:
        return [str(self.cond_reg)]


@dataclass(frozen=True)
class Return_(InstructionBase):
    """RETURN: return from the current function."""

    value_reg: Register | None = None

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.RETURN

    @property
    def operands(self) -> list[Any]:
        return [str(self.value_reg)] if self.value_reg is not None else []


@dataclass(frozen=True)
class Throw_(InstructionBase):
    """THROW: raise an exception."""

    value_reg: Register | None = None

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.THROW

    @property
    def operands(self) -> list[Any]:
        return [str(self.value_reg)] if self.value_reg is not None else []


# ── Exceptions ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TryPush(InstructionBase):
    """TRY_PUSH: push an exception handler onto the exception stack."""

    catch_labels: tuple[CodeLabel, ...] = ()
    finally_label: CodeLabel = NO_LABEL
    end_label: CodeLabel = NO_LABEL

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.TRY_PUSH

    @property
    def operands(self) -> list[Any]:
        return [list(self.catch_labels), self.finally_label, self.end_label]


@dataclass(frozen=True)
class TryPop(InstructionBase):
    """TRY_POP: pop the top exception handler."""

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.TRY_POP

    @property
    def operands(self) -> list[Any]:
        return []


# ── Regions (COBOL byte-addressable memory) ──────────────────────


@dataclass(frozen=True)
class AllocRegion(InstructionBase):
    """ALLOC_REGION: allocate a byte region of a given size."""

    result_reg: Register = NO_REGISTER
    size_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.ALLOC_REGION

    @property
    def operands(self) -> list[Any]:
        return [str(self.size_reg)]


@dataclass(frozen=True)
class LoadRegion(InstructionBase):
    """LOAD_REGION: read bytes from a region at offset."""

    result_reg: Register = NO_REGISTER
    region_reg: Register = NO_REGISTER
    offset_reg: Register = NO_REGISTER
    length: int = 0

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_REGION

    @property
    def operands(self) -> list[Any]:
        return [str(self.region_reg), str(self.offset_reg), self.length]


@dataclass(frozen=True)
class WriteRegion(InstructionBase):
    """WRITE_REGION: write bytes into a region at offset."""

    region_reg: Register = NO_REGISTER
    offset_reg: Register = NO_REGISTER
    length: int = 0
    value_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.WRITE_REGION

    @property
    def operands(self) -> list[Any]:
        return [
            str(self.region_reg),
            str(self.offset_reg),
            self.length,
            str(self.value_reg),
        ]


# ── Continuations (COBOL PERFORM) ───────────────────────────────


@dataclass(frozen=True)
class SetContinuation(InstructionBase):
    """SET_CONTINUATION: associate a name with a target label."""

    name: str = ""
    target_label: CodeLabel = NO_LABEL

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.SET_CONTINUATION

    @property
    def operands(self) -> list[Any]:
        return [self.name, self.target_label]


@dataclass(frozen=True)
class ResumeContinuation(InstructionBase):
    """RESUME_CONTINUATION: branch to the label associated with a name."""

    name: str = ""

    # ── IRInstruction-compat fields ──
    result_reg: Register = NO_REGISTER
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.RESUME_CONTINUATION

    @property
    def operands(self) -> list[Any]:
        return [self.name]


# ── Union type ───────────────────────────────────────────────────

Instruction = Union[
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Symbolic,
    Binop,
    Unop,
    CallFunction,
    CallMethod,
    CallUnknown,
    CallCtorFunction,
    LoadField,
    StoreField,
    LoadFieldIndirect,
    LoadIndex,
    StoreIndex,
    LoadIndirect,
    StoreIndirect,
    AddressOf,
    NewObject,
    NewArray,
    Label_,
    Branch,
    BranchIf,
    Return_,
    Throw_,
    TryPush,
    TryPop,
    AllocRegion,
    LoadRegion,
    WriteRegion,
    SetContinuation,
    ResumeContinuation,
]


# ── Conversion: flat → typed ─────────────────────────────────────

# Dispatch table: Opcode → converter function.
# Each converter takes (IRInstruction) → Instruction.


def _const(inst: IRInstruction) -> Const:
    return Const(
        result_reg=inst.result_reg,
        value=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


def _load_var(inst: IRInstruction) -> LoadVar:
    return LoadVar(
        result_reg=inst.result_reg,
        name=VarName(str(inst.operands[0])) if inst.operands else NO_VAR_NAME,
        source_location=inst.source_location,
    )


def _decl_var(inst: IRInstruction) -> DeclVar:
    ops = inst.operands
    return DeclVar(
        name=VarName(str(ops[0])) if len(ops) >= 1 else NO_VAR_NAME,
        value_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _store_var(inst: IRInstruction) -> StoreVar:
    ops = inst.operands
    return StoreVar(
        name=VarName(str(ops[0])) if len(ops) >= 1 else NO_VAR_NAME,
        value_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _symbolic(inst: IRInstruction) -> Symbolic:
    return Symbolic(
        result_reg=inst.result_reg,
        hint=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


def _binop(inst: IRInstruction) -> Binop:
    ops = inst.operands
    raw_op = getattr(ops[0], "value", str(ops[0])) if ops else ""
    return Binop(
        result_reg=inst.result_reg,
        operator=resolve_binop(raw_op) if raw_op else BinopKind.ADD,
        left=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        right=Register(str(ops[2])) if len(ops) >= 3 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _unop(inst: IRInstruction) -> Unop:
    ops = inst.operands
    raw_op = getattr(ops[0], "value", str(ops[0])) if ops else ""
    return Unop(
        result_reg=inst.result_reg,
        operator=resolve_unop(raw_op) if raw_op else UnopKind.NEG,
        operand=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _call_function(inst: IRInstruction) -> CallFunction:
    ops = inst.operands
    raw_args = ops[1:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else _as_register(a) for a in raw_args
    )
    return CallFunction(
        result_reg=inst.result_reg,
        func_name=FuncName(str(ops[0])) if ops else NO_FUNC_NAME,
        args=args,
        source_location=inst.source_location,
    )


def _call_method(inst: IRInstruction) -> CallMethod:
    ops = inst.operands
    raw_args = ops[2:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else _as_register(a) for a in raw_args
    )
    return CallMethod(
        result_reg=inst.result_reg,
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        method_name=FuncName(str(ops[1])) if len(ops) >= 2 else NO_FUNC_NAME,
        args=args,
        source_location=inst.source_location,
    )


def _call_unknown(inst: IRInstruction) -> CallUnknown:
    ops = inst.operands
    raw_args = ops[1:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else _as_register(a) for a in raw_args
    )
    return CallUnknown(
        result_reg=inst.result_reg,
        target_reg=Register(str(ops[0])) if ops else NO_REGISTER,
        args=args,
        source_location=inst.source_location,
    )


def _call_ctor(inst: IRInstruction) -> CallCtorFunction:
    ops = inst.operands
    raw_args = ops[1:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else _as_register(a) for a in raw_args
    )
    raw_hint = str(ops[0]) if ops else ""
    return CallCtorFunction(
        result_reg=inst.result_reg,
        func_name=FuncName(raw_hint) if raw_hint else NO_FUNC_NAME,
        type_hint=scalar(raw_hint) if raw_hint else UNKNOWN,
        args=args,
        source_location=inst.source_location,
    )


def _load_field(inst: IRInstruction) -> LoadField:
    ops = inst.operands
    return LoadField(
        result_reg=inst.result_reg,
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        field_name=FieldName(str(ops[1])) if len(ops) >= 2 else NO_FIELD_NAME,
        source_location=inst.source_location,
    )


def _store_field(inst: IRInstruction) -> StoreField:
    ops = inst.operands
    return StoreField(
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        field_name=FieldName(str(ops[1])) if len(ops) >= 2 else NO_FIELD_NAME,
        value_reg=Register(str(ops[2])) if len(ops) >= 3 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _load_field_indirect(inst: IRInstruction) -> LoadFieldIndirect:
    ops = inst.operands
    return LoadFieldIndirect(
        result_reg=inst.result_reg,
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        name_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _load_index(inst: IRInstruction) -> LoadIndex:
    ops = inst.operands
    return LoadIndex(
        result_reg=inst.result_reg,
        arr_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        index_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _store_index(inst: IRInstruction) -> StoreIndex:
    ops = inst.operands
    vr = (
        ops[2]
        if len(ops) >= 3 and isinstance(ops[2], SpreadArguments)
        else (Register(str(ops[2])) if len(ops) >= 3 else NO_REGISTER)
    )
    return StoreIndex(
        arr_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        index_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        value_reg=vr,
        source_location=inst.source_location,
    )


def _load_indirect(inst: IRInstruction) -> LoadIndirect:
    return LoadIndirect(
        result_reg=inst.result_reg,
        ptr_reg=Register(str(inst.operands[0])) if inst.operands else NO_REGISTER,
        source_location=inst.source_location,
    )


def _store_indirect(inst: IRInstruction) -> StoreIndirect:
    ops = inst.operands
    return StoreIndirect(
        ptr_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        value_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _address_of(inst: IRInstruction) -> AddressOf:
    return AddressOf(
        result_reg=inst.result_reg,
        var_name=VarName(str(inst.operands[0])) if inst.operands else NO_VAR_NAME,
        source_location=inst.source_location,
    )


def _new_object(inst: IRInstruction) -> NewObject:
    raw = str(inst.operands[0]) if inst.operands else ""
    return NewObject(
        result_reg=inst.result_reg,
        type_hint=scalar(raw) if raw else UNKNOWN,
        source_location=inst.source_location,
    )


def _new_array(inst: IRInstruction) -> NewArray:
    ops = inst.operands
    raw = str(ops[0]) if len(ops) >= 1 else ""
    return NewArray(
        result_reg=inst.result_reg,
        type_hint=scalar(raw) if raw else UNKNOWN,
        size_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _label(inst: IRInstruction) -> Label_:
    return Label_(label=inst.label, source_location=inst.source_location)


def _branch(inst: IRInstruction) -> Branch:
    return Branch(label=inst.label, source_location=inst.source_location)


def _branch_if(inst: IRInstruction) -> BranchIf:
    return BranchIf(
        cond_reg=Register(str(inst.operands[0])) if inst.operands else NO_REGISTER,
        branch_targets=tuple(inst.branch_targets),
        source_location=inst.source_location,
    )


def _return(inst: IRInstruction) -> Return_:
    return Return_(
        value_reg=Register(str(inst.operands[0])) if inst.operands else None,
        source_location=inst.source_location,
    )


def _throw(inst: IRInstruction) -> Throw_:
    return Throw_(
        value_reg=Register(str(inst.operands[0])) if inst.operands else None,
        source_location=inst.source_location,
    )


def _try_push(inst: IRInstruction) -> TryPush:
    ops = inst.operands
    catch = tuple(ops[0]) if len(ops) >= 1 and isinstance(ops[0], list) else ()
    finally_lbl = ops[1] if len(ops) >= 2 else NO_LABEL
    end_lbl = ops[2] if len(ops) >= 3 else NO_LABEL
    return TryPush(
        catch_labels=catch,
        finally_label=finally_lbl,
        end_label=end_lbl,
        source_location=inst.source_location,
    )


def _try_pop(inst: IRInstruction) -> TryPop:
    return TryPop(source_location=inst.source_location)


def _alloc_region(inst: IRInstruction) -> AllocRegion:
    return AllocRegion(
        result_reg=inst.result_reg,
        size_reg=Register(str(inst.operands[0])) if inst.operands else NO_REGISTER,
        source_location=inst.source_location,
    )


def _load_region(inst: IRInstruction) -> LoadRegion:
    ops = inst.operands
    return LoadRegion(
        result_reg=inst.result_reg,
        region_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        offset_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        length=int(ops[2]) if len(ops) >= 3 else 0,
        source_location=inst.source_location,
    )


def _write_region(inst: IRInstruction) -> WriteRegion:
    ops = inst.operands
    return WriteRegion(
        region_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        offset_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        length=int(ops[2]) if len(ops) >= 3 else 0,
        value_reg=Register(str(ops[3])) if len(ops) >= 4 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _set_continuation(inst: IRInstruction) -> SetContinuation:
    ops = inst.operands
    return SetContinuation(
        name=str(ops[0]) if len(ops) >= 1 else "",
        target_label=ops[1] if len(ops) >= 2 else NO_LABEL,
        source_location=inst.source_location,
    )


def _resume_continuation(inst: IRInstruction) -> ResumeContinuation:
    return ResumeContinuation(
        name=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


_TO_TYPED: dict[Opcode, object] = {
    Opcode.CONST: _const,
    Opcode.LOAD_VAR: _load_var,
    Opcode.DECL_VAR: _decl_var,
    Opcode.STORE_VAR: _store_var,
    Opcode.SYMBOLIC: _symbolic,
    Opcode.BINOP: _binop,
    Opcode.UNOP: _unop,
    Opcode.CALL_FUNCTION: _call_function,
    Opcode.CALL_METHOD: _call_method,
    Opcode.CALL_UNKNOWN: _call_unknown,
    Opcode.CALL_CTOR: _call_ctor,
    Opcode.LOAD_FIELD: _load_field,
    Opcode.STORE_FIELD: _store_field,
    Opcode.LOAD_FIELD_INDIRECT: _load_field_indirect,
    Opcode.LOAD_INDEX: _load_index,
    Opcode.STORE_INDEX: _store_index,
    Opcode.LOAD_INDIRECT: _load_indirect,
    Opcode.STORE_INDIRECT: _store_indirect,
    Opcode.ADDRESS_OF: _address_of,
    Opcode.NEW_OBJECT: _new_object,
    Opcode.NEW_ARRAY: _new_array,
    Opcode.LABEL: _label,
    Opcode.BRANCH: _branch,
    Opcode.BRANCH_IF: _branch_if,
    Opcode.RETURN: _return,
    Opcode.THROW: _throw,
    Opcode.TRY_PUSH: _try_push,
    Opcode.TRY_POP: _try_pop,
    Opcode.ALLOC_REGION: _alloc_region,
    Opcode.LOAD_REGION: _load_region,
    Opcode.WRITE_REGION: _write_region,
    Opcode.SET_CONTINUATION: _set_continuation,
    Opcode.RESUME_CONTINUATION: _resume_continuation,
}


def _to_typed(inst: Any) -> Instruction:
    """Convert a flat instruction-like object to a per-opcode typed instruction.

    If *inst* is already a typed instruction (InstructionBase subclass),
    it is returned as-is.  Otherwise *inst* must be duck-typed with
    ``.opcode``, ``.result_reg``, ``.operands``, ``.label``,
    ``.branch_targets``, and ``.source_location`` attributes.
    """
    if isinstance(inst, InstructionBase):
        return inst
    converter = _TO_TYPED.get(inst.opcode)
    if converter is None:
        raise ValueError(f"Unknown opcode: {inst.opcode}")
    return converter(inst)
