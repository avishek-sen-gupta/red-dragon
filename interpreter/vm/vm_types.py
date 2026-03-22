"""Symbolic VM — data types (pure data, no business logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from interpreter.constants import TypeName
from interpreter.types.type_expr import TypeExpr, UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed

# ── Data types ───────────────────────────────────────────────────


@dataclass
class SymbolicValue:
    name: str
    type_hint: str | None = None
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"__symbolic__": True, "name": self.name}
        if self.type_hint:
            d["type_hint"] = self.type_hint
        if self.constraints:
            d["constraints"] = self.constraints
        return d


@dataclass(frozen=True)
class Pointer:
    """Typed pointer — (base heap address, element offset).

    Models C/C++/Rust pointers. Pointer arithmetic produces new Pointer
    objects with adjusted offsets. Dereferencing reads/writes
    heap[base].fields[str(offset)].
    """

    base: str
    offset: int = 0


@dataclass
class HeapObject:
    type_hint: TypeExpr = UNKNOWN
    fields: dict[str, TypedValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type_hint": str(self.type_hint) or None,
            "fields": {k: _serialize_value(v) for k, v in self.fields.items()},
        }


@dataclass
class ClosureEnvironment:
    """Shared mutable environment for closure capture-by-reference."""

    bindings: dict[str, TypedValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: _serialize_value(v) for k, v in self.bindings.items()}


@dataclass
class ExceptionHandler:
    """Exception handler pushed by TRY_PUSH, popped by TRY_POP or THROW."""

    catch_labels: list[str] = field(default_factory=list)
    finally_label: str = ""
    end_label: str = ""


@dataclass
class StackFrame:
    function_name: str
    registers: dict[str, TypedValue] = field(default_factory=dict)
    local_vars: dict[str, TypedValue] = field(default_factory=dict)
    return_label: str | None = None
    return_ip: int | None = None  # ip to resume at in caller block
    result_reg: str | None = None  # caller's register for return value
    closure_env_id: str = ""
    captured_var_names: frozenset[str] = field(default_factory=frozenset)
    var_heap_aliases: dict[str, Pointer] = field(default_factory=dict)
    is_ctor: bool = False

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "function_name": self.function_name,
            "registers": {k: _serialize_value(v) for k, v in self.registers.items()},
            "local_vars": {k: _serialize_value(v) for k, v in self.local_vars.items()},
            "return_label": self.return_label,
        }
        if self.closure_env_id:
            d["closure_env_id"] = self.closure_env_id
        return d


def _serialize_value(v: Any) -> Any:
    from interpreter.types.typed_value import TypedValue

    if isinstance(v, TypedValue):
        return _serialize_value(v.value)
    if isinstance(v, SymbolicValue):
        return v.to_dict()
    if isinstance(v, HeapObject):
        return v.to_dict()
    if isinstance(v, Pointer):
        return {"__pointer__": True, "base": v.base, "offset": v.offset}
    return v


@dataclass
class VMState:
    heap: dict[str, HeapObject] = field(default_factory=dict)
    call_stack: list[StackFrame] = field(default_factory=list)
    path_conditions: list[str] = field(default_factory=list)
    symbolic_counter: int = 0
    closures: dict[str, ClosureEnvironment] = field(default_factory=dict)
    regions: dict[str, bytearray] = field(default_factory=dict)
    continuations: dict[str, str] = field(default_factory=dict)
    exception_stack: list[ExceptionHandler] = field(default_factory=list)
    data_layout: dict[str, dict] = field(default_factory=dict)
    io_provider: Any = (
        None  # Optional CobolIOProvider — Any to avoid COBOL import in core VM
    )

    def fresh_symbolic(self, hint: str = "") -> SymbolicValue:
        name = f"sym_{self.symbolic_counter}"
        self.symbolic_counter += 1
        return SymbolicValue(name=name, type_hint=hint or None)

    @property
    def current_frame(self) -> StackFrame:
        return self.call_stack[-1]

    def to_dict(self) -> dict:
        result: dict[str, Any] = {
            "heap": {k: v.to_dict() for k, v in self.heap.items()},
            "call_stack": [f.to_dict() for f in self.call_stack],
            "path_conditions": self.path_conditions,
            "symbolic_counter": self.symbolic_counter,
        }
        if self.closures:
            result["closures"] = {
                label: env.to_dict() for label, env in self.closures.items()
            }
        if self.regions:
            result["regions"] = {
                addr: list(data) for addr, data in self.regions.items()
            }
        if self.continuations:
            result["continuations"] = dict(self.continuations)
        if self.data_layout:
            result["data_layout"] = dict(self.data_layout)
        return result


# ── StateUpdate schema (LLM output) ─────────────────────────────


class HeapWrite(BaseModel):
    obj_addr: str
    field: str
    value: Any


class NewObject(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    addr: str
    type_hint: TypeExpr = UNKNOWN


class RegionWrite(BaseModel):
    region_addr: str
    offset: int
    data: list[int]


@dataclass
class BuiltinResult:
    """Uniform return type for all builtins.

    Pure builtins return BuiltinResult(value=...) with empty side-effect lists.
    Heap-mutating builtins express mutations as new_objects + heap_writes.
    """

    value: Any
    new_objects: list[NewObject] = field(default_factory=list)
    heap_writes: list[HeapWrite] = field(default_factory=list)


class StackFramePush(BaseModel):
    function_name: str
    return_label: str | None = None
    closure_env_id: str = ""
    captured_var_names: list[str] = []
    is_ctor: bool = False


VOID_RETURN: TypedValue = typed(None, scalar(TypeName.VOID))


class StateUpdate(BaseModel):
    register_writes: dict[str, Any] = {}
    var_writes: dict[str, Any] = {}
    heap_writes: list[HeapWrite] = []
    new_objects: list[NewObject] = []
    region_writes: list[RegionWrite] = []
    new_regions: dict[str, int] = {}
    continuation_writes: dict[str, str] = {}
    continuation_clear: str = ""
    next_label: str | None = None
    call_push: StackFramePush | None = None
    call_pop: bool = False
    return_value: Any = VOID_RETURN
    path_condition: str | None = None
    reasoning: str = ""


# ── ExecutionResult — replaces return None as "LLM needed" sentinel ──


@dataclass
class ExecutionResult:
    """Result of attempting local instruction execution."""

    handled: bool
    update: StateUpdate = field(default_factory=lambda: StateUpdate(reasoning=""))

    @classmethod
    def not_handled(cls) -> ExecutionResult:
        return cls(handled=False)

    @classmethod
    def success(cls, update: StateUpdate) -> ExecutionResult:
        return cls(handled=True, update=update)
