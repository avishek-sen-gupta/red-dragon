"""Per-opcode typed instruction classes.

Replaces the flat ``IRInstruction.operands: list[Any]`` with named, typed
fields on per-opcode frozen dataclasses.

Migration adapter: ``to_typed()`` converts flat → typed, ``to_flat()``
converts typed → flat.  Both directions are lossless; the full test suite
must survive ``to_typed(inst).to_flat() == inst`` for every instruction.
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
    IRInstruction,
    NO_LABEL,
    NO_SOURCE_LOCATION,
    Opcode,
    SourceLocation,
    SpreadArguments,
)
from interpreter.register import NO_REGISTER, Register


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

    COBOL IR places literal ints/floats directly in call operands; those
    must NOT be wrapped.  Only strings that begin with '%' are register refs.
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
        """Apply fn to every Register-typed field, return a new instruction."""
        changes: dict[str, object] = {}
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            hint = hints.get(f.name, f.type)
            val = getattr(self, f.name)
            if isinstance(val, Register):
                changes[f.name] = fn(val)
            elif val is None and _is_optional_register(hint):
                pass  # None stays None
            elif isinstance(val, tuple) and _is_register_args_tuple(hint):
                changes[f.name] = tuple(
                    (
                        SpreadArguments(register=fn(a.register))
                        if isinstance(a, SpreadArguments)
                        else (
                            fn(a) if isinstance(a, Register) else a
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
        return str(to_flat(self))


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
    name: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_VAR

    @property
    def operands(self) -> list[Any]:
        return [self.name]


@dataclass(frozen=True)
class DeclVar(InstructionBase):
    """DECL_VAR: declare a variable and assign a value from a register."""

    name: str = ""
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
        return [self.name, str(self.value_reg)]


@dataclass(frozen=True)
class StoreVar(InstructionBase):
    """STORE_VAR: assign to an existing variable from a register."""

    name: str = ""
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
        return [self.name, str(self.value_reg)]


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
    operator: str = ""
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
            self.operator,
            str(self.left) if isinstance(self.left, Register) else self.left,
            str(self.right) if isinstance(self.right, Register) else self.right,
        ]


@dataclass(frozen=True)
class Unop(InstructionBase):
    """UNOP: unary operation (operator, operand register)."""

    result_reg: Register = NO_REGISTER
    operator: str = ""
    operand: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.UNOP

    @property
    def operands(self) -> list[Any]:
        return [self.operator, str(self.operand)]


# ── Calls ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CallFunction(InstructionBase):
    """CALL_FUNCTION: call a named function with arguments."""

    result_reg: Register = NO_REGISTER
    func_name: str = ""
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
            self.func_name,
            *(str(a) if isinstance(a, Register) else a for a in self.args),
        ]


@dataclass(frozen=True)
class CallMethod(InstructionBase):
    """CALL_METHOD: call a method on an object."""

    result_reg: Register = NO_REGISTER
    obj_reg: Register = NO_REGISTER
    method_name: str = ""
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
            self.method_name,
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


# ── Memory — Fields ──────────────────────────────────────────────


@dataclass(frozen=True)
class LoadField(InstructionBase):
    """LOAD_FIELD: load a named field from an object."""

    result_reg: Register = NO_REGISTER
    obj_reg: Register = NO_REGISTER
    field_name: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.LOAD_FIELD

    @property
    def operands(self) -> list[Any]:
        return [str(self.obj_reg), self.field_name]


@dataclass(frozen=True)
class StoreField(InstructionBase):
    """STORE_FIELD: store a value into a named field on an object."""

    obj_reg: Register = NO_REGISTER
    field_name: str = ""
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
        return [str(self.obj_reg), self.field_name, str(self.value_reg)]


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
    value_reg: Register = NO_REGISTER

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
    var_name: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.ADDRESS_OF

    @property
    def operands(self) -> list[Any]:
        return [self.var_name]


# ── Objects ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewObject(InstructionBase):
    """NEW_OBJECT: allocate a new object on the heap."""

    result_reg: Register = NO_REGISTER
    type_hint: str = ""

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.NEW_OBJECT

    @property
    def operands(self) -> list[Any]:
        return [self.type_hint] if self.type_hint else []


@dataclass(frozen=True)
class NewArray(InstructionBase):
    """NEW_ARRAY: allocate a new array/list/dict on the heap."""

    result_reg: Register = NO_REGISTER
    type_hint: str = ""
    size_reg: Register = NO_REGISTER

    # ── IRInstruction-compat fields ──
    label: CodeLabel = NO_LABEL
    branch_targets: tuple[CodeLabel, ...] = ()

    @property
    def opcode(self) -> Opcode:
        return Opcode.NEW_ARRAY

    @property
    def operands(self) -> list[Any]:
        return [self.type_hint, str(self.size_reg)]


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
        name=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


def _decl_var(inst: IRInstruction) -> DeclVar:
    ops = inst.operands
    return DeclVar(
        name=str(ops[0]) if len(ops) >= 1 else "",
        value_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _store_var(inst: IRInstruction) -> StoreVar:
    ops = inst.operands
    return StoreVar(
        name=str(ops[0]) if len(ops) >= 1 else "",
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
    return Binop(
        result_reg=inst.result_reg,
        operator=str(ops[0]) if len(ops) >= 1 else "",
        left=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        right=Register(str(ops[2])) if len(ops) >= 3 else NO_REGISTER,
        source_location=inst.source_location,
    )


def _unop(inst: IRInstruction) -> Unop:
    ops = inst.operands
    return Unop(
        result_reg=inst.result_reg,
        operator=str(ops[0]) if len(ops) >= 1 else "",
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
        func_name=str(ops[0]) if ops else "",
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
        method_name=str(ops[1]) if len(ops) >= 2 else "",
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


def _load_field(inst: IRInstruction) -> LoadField:
    ops = inst.operands
    return LoadField(
        result_reg=inst.result_reg,
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        field_name=str(ops[1]) if len(ops) >= 2 else "",
        source_location=inst.source_location,
    )


def _store_field(inst: IRInstruction) -> StoreField:
    ops = inst.operands
    return StoreField(
        obj_reg=Register(str(ops[0])) if len(ops) >= 1 else NO_REGISTER,
        field_name=str(ops[1]) if len(ops) >= 2 else "",
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
        var_name=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


def _new_object(inst: IRInstruction) -> NewObject:
    return NewObject(
        result_reg=inst.result_reg,
        type_hint=str(inst.operands[0]) if inst.operands else "",
        source_location=inst.source_location,
    )


def _new_array(inst: IRInstruction) -> NewArray:
    ops = inst.operands
    return NewArray(
        result_reg=inst.result_reg,
        type_hint=str(ops[0]) if len(ops) >= 1 else "",
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


def to_typed(inst: IRInstruction) -> Instruction:
    """Convert a flat IRInstruction to a per-opcode typed instruction."""
    converter = _TO_TYPED.get(inst.opcode)
    if converter is None:
        raise ValueError(f"Unknown opcode: {inst.opcode}")
    return converter(inst)


# ── Conversion: typed → flat ─────────────────────────────────────

# Dispatch table: type → converter function.
# Each converter takes (Instruction) → IRInstruction.


def _flat_const(t: Const) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.CONST,
        result_reg=t.result_reg,
        operands=[t.value] if t.value != "" else [],
        source_location=t.source_location,
    )


def _flat_load_var(t: LoadVar) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_VAR,
        result_reg=t.result_reg,
        operands=[t.name],
        source_location=t.source_location,
    )


def _flat_decl_var(t: DeclVar) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.DECL_VAR,
        operands=[t.name, str(t.value_reg)],
        source_location=t.source_location,
    )


def _flat_store_var(t: StoreVar) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.STORE_VAR,
        operands=[t.name, str(t.value_reg)],
        source_location=t.source_location,
    )


def _flat_symbolic(t: Symbolic) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.SYMBOLIC,
        result_reg=t.result_reg,
        operands=[t.hint] if t.hint else [],
        source_location=t.source_location,
    )


def _flat_binop(t: Binop) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.BINOP,
        result_reg=t.result_reg,
        operands=[t.operator, str(t.left), str(t.right)],
        source_location=t.source_location,
    )


def _flat_unop(t: Unop) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.UNOP,
        result_reg=t.result_reg,
        operands=[t.operator, str(t.operand)],
        source_location=t.source_location,
    )


def _flat_call_function(t: CallFunction) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.CALL_FUNCTION,
        result_reg=t.result_reg,
        operands=[
            t.func_name,
            *(str(a) if isinstance(a, Register) else a for a in t.args),
        ],
        source_location=t.source_location,
    )


def _flat_call_method(t: CallMethod) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.CALL_METHOD,
        result_reg=t.result_reg,
        operands=[
            str(t.obj_reg),
            t.method_name,
            *(str(a) if isinstance(a, Register) else a for a in t.args),
        ],
        source_location=t.source_location,
    )


def _flat_call_unknown(t: CallUnknown) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.CALL_UNKNOWN,
        result_reg=t.result_reg,
        operands=[
            str(t.target_reg),
            *(str(a) if isinstance(a, Register) else a for a in t.args),
        ],
        source_location=t.source_location,
    )


def _flat_load_field(t: LoadField) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_FIELD,
        result_reg=t.result_reg,
        operands=[str(t.obj_reg), t.field_name],
        source_location=t.source_location,
    )


def _flat_store_field(t: StoreField) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.STORE_FIELD,
        operands=[str(t.obj_reg), t.field_name, str(t.value_reg)],
        source_location=t.source_location,
    )


def _flat_load_field_indirect(t: LoadFieldIndirect) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_FIELD_INDIRECT,
        result_reg=t.result_reg,
        operands=[str(t.obj_reg), str(t.name_reg)],
        source_location=t.source_location,
    )


def _flat_load_index(t: LoadIndex) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_INDEX,
        result_reg=t.result_reg,
        operands=[str(t.arr_reg), str(t.index_reg)],
        source_location=t.source_location,
    )


def _flat_store_index(t: StoreIndex) -> IRInstruction:
    vr = t.value_reg if isinstance(t.value_reg, SpreadArguments) else str(t.value_reg)
    return IRInstruction(
        opcode=Opcode.STORE_INDEX,
        operands=[str(t.arr_reg), str(t.index_reg), vr],
        source_location=t.source_location,
    )


def _flat_load_indirect(t: LoadIndirect) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_INDIRECT,
        result_reg=t.result_reg,
        operands=[str(t.ptr_reg)],
        source_location=t.source_location,
    )


def _flat_store_indirect(t: StoreIndirect) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.STORE_INDIRECT,
        operands=[str(t.ptr_reg), str(t.value_reg)],
        source_location=t.source_location,
    )


def _flat_address_of(t: AddressOf) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.ADDRESS_OF,
        result_reg=t.result_reg,
        operands=[t.var_name],
        source_location=t.source_location,
    )


def _flat_new_object(t: NewObject) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.NEW_OBJECT,
        result_reg=t.result_reg,
        operands=[t.type_hint] if t.type_hint else [],
        source_location=t.source_location,
    )


def _flat_new_array(t: NewArray) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.NEW_ARRAY,
        result_reg=t.result_reg,
        operands=[t.type_hint, str(t.size_reg)],
        source_location=t.source_location,
    )


def _flat_label(t: Label_) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LABEL,
        label=t.label,
        source_location=t.source_location,
    )


def _flat_branch(t: Branch) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.BRANCH,
        label=t.label,
        source_location=t.source_location,
    )


def _flat_branch_if(t: BranchIf) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.BRANCH_IF,
        operands=[str(t.cond_reg)],
        branch_targets=list(t.branch_targets),
        source_location=t.source_location,
    )


def _flat_return(t: Return_) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.RETURN,
        operands=[str(t.value_reg)] if t.value_reg is not None else [],
        source_location=t.source_location,
    )


def _flat_throw(t: Throw_) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.THROW,
        operands=[str(t.value_reg)] if t.value_reg is not None else [],
        source_location=t.source_location,
    )


def _flat_try_push(t: TryPush) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.TRY_PUSH,
        operands=[list(t.catch_labels), t.finally_label, t.end_label],
        source_location=t.source_location,
    )


def _flat_try_pop(t: TryPop) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.TRY_POP,
        source_location=t.source_location,
    )


def _flat_alloc_region(t: AllocRegion) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.ALLOC_REGION,
        result_reg=t.result_reg,
        operands=[str(t.size_reg)],
        source_location=t.source_location,
    )


def _flat_load_region(t: LoadRegion) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.LOAD_REGION,
        result_reg=t.result_reg,
        operands=[str(t.region_reg), str(t.offset_reg), t.length],
        source_location=t.source_location,
    )


def _flat_write_region(t: WriteRegion) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.WRITE_REGION,
        operands=[str(t.region_reg), str(t.offset_reg), t.length, str(t.value_reg)],
        source_location=t.source_location,
    )


def _flat_set_continuation(t: SetContinuation) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.SET_CONTINUATION,
        operands=[t.name, t.target_label],
        source_location=t.source_location,
    )


def _flat_resume_continuation(t: ResumeContinuation) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.RESUME_CONTINUATION,
        operands=[t.name],
        source_location=t.source_location,
    )


_TO_FLAT: dict[type, object] = {
    Const: _flat_const,
    LoadVar: _flat_load_var,
    DeclVar: _flat_decl_var,
    StoreVar: _flat_store_var,
    Symbolic: _flat_symbolic,
    Binop: _flat_binop,
    Unop: _flat_unop,
    CallFunction: _flat_call_function,
    CallMethod: _flat_call_method,
    CallUnknown: _flat_call_unknown,
    LoadField: _flat_load_field,
    StoreField: _flat_store_field,
    LoadFieldIndirect: _flat_load_field_indirect,
    LoadIndex: _flat_load_index,
    StoreIndex: _flat_store_index,
    LoadIndirect: _flat_load_indirect,
    StoreIndirect: _flat_store_indirect,
    AddressOf: _flat_address_of,
    NewObject: _flat_new_object,
    NewArray: _flat_new_array,
    Label_: _flat_label,
    Branch: _flat_branch,
    BranchIf: _flat_branch_if,
    Return_: _flat_return,
    Throw_: _flat_throw,
    TryPush: _flat_try_push,
    TryPop: _flat_try_pop,
    AllocRegion: _flat_alloc_region,
    LoadRegion: _flat_load_region,
    WriteRegion: _flat_write_region,
    SetContinuation: _flat_set_continuation,
    ResumeContinuation: _flat_resume_continuation,
}


def to_flat(typed: Instruction) -> IRInstruction:
    """Convert a per-opcode typed instruction back to flat IRInstruction."""
    converter = _TO_FLAT.get(type(typed))
    if converter is None:
        raise ValueError(f"Unknown instruction type: {type(typed).__name__}")
    return converter(typed)
