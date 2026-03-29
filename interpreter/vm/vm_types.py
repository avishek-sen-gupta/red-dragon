"""Symbolic VM — data types (pure data, no business logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from interpreter.address import Address
from interpreter.constants import TypeName
from interpreter.field_name import FieldName, FieldKind
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register, NO_REGISTER
from interpreter.types.type_expr import TypeExpr, UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed
from interpreter.var_name import VarName

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

    base: Address
    offset: int = 0


@dataclass
class HeapObject:
    type_hint: TypeExpr = UNKNOWN
    fields: dict[FieldName, TypedValue] = field(default_factory=dict)

    def is_present(self) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type_hint": str(self.type_hint) or None,
            "fields": {str(k): _serialize_value(v) for k, v in self.fields.items()},
        }


@dataclass(eq=False)
class NullHeapObject(HeapObject):
    """Null object: no heap object at this address. Use .is_present() for checks."""

    def is_present(self) -> bool:
        return False


NO_HEAP_OBJECT = NullHeapObject()


@dataclass
class ClosureEnvironment:
    """Shared mutable environment for closure capture-by-reference."""

    bindings: dict[VarName, TypedValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {str(k): _serialize_value(v) for k, v in self.bindings.items()}


@dataclass
class ExceptionHandler:
    """Exception handler pushed by TRY_PUSH, popped by TRY_POP or THROW."""

    catch_labels: list[CodeLabel] = field(default_factory=list)
    finally_label: CodeLabel | None = None
    end_label: CodeLabel | None = None


@dataclass
class StackFrame:
    function_name: FuncName
    registers: dict[Register, TypedValue] = field(default_factory=dict)
    local_vars: dict[VarName, TypedValue] = field(default_factory=dict)
    return_label: CodeLabel | None = None
    return_ip: int | None = None  # ip to resume at in caller block
    result_reg: Register = field(
        default_factory=lambda: NO_REGISTER
    )  # caller's register for return value
    closure_env_id: str = ""
    captured_var_names: frozenset[VarName] = field(default_factory=frozenset)
    var_heap_aliases: dict[VarName, Pointer] = field(default_factory=dict)
    is_ctor: bool = False

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "function_name": str(self.function_name),
            "registers": {
                str(k): _serialize_value(v) for k, v in self.registers.items()
            },
            "local_vars": {
                str(k): _serialize_value(v) for k, v in self.local_vars.items()
            },
            "return_label": str(self.return_label) if self.return_label else None,
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
        return {"__pointer__": True, "base": str(v.base), "offset": v.offset}
    return v


@dataclass
class VMState:
    _heap: dict[Address, HeapObject] = field(default_factory=dict)
    call_stack: list[StackFrame] = field(default_factory=list)
    path_conditions: list[str] = field(default_factory=list)
    symbolic_counter: int = 0
    closures: dict[str, ClosureEnvironment] = field(default_factory=dict)
    _regions: dict[Address, bytearray] = field(default_factory=dict)
    continuations: dict[str, CodeLabel] = field(default_factory=dict)
    exception_stack: list[ExceptionHandler] = field(default_factory=list)
    data_layout: dict[str, dict] = field(default_factory=dict)
    io_provider: Any = (
        None  # Optional CobolIOProvider — Any to avoid COBOL import in core VM
    )

    def heap_get(self, addr: Address) -> HeapObject:
        """Get heap object by address. Returns NO_HEAP_OBJECT if not found."""
        return self._heap.get(addr, NO_HEAP_OBJECT)

    def heap_set(self, addr: Address, obj: HeapObject) -> None:
        """Set heap object at address."""
        self._heap[addr] = obj

    def heap_contains(self, addr: Address) -> bool:
        """Check if address exists in heap."""
        return addr in self._heap

    def heap_ensure(self, addr: Address) -> HeapObject:
        """Get or create a HeapObject at addr (type_hint=UNKNOWN)."""
        if addr not in self._heap:
            self._heap[addr] = HeapObject()
        return self._heap[addr]

    def heap_items(self):
        """Iterate over all (address, HeapObject) pairs."""
        return self._heap.items()

    def heap_keys(self):
        """Iterate over all heap addresses."""
        return self._heap.keys()

    def region_get(self, addr: Address) -> bytearray | None:
        """Get region data by address."""
        return self._regions.get(addr)

    def region_set(self, addr: Address, data: bytearray) -> None:
        """Set region data at address."""
        self._regions[addr] = data

    def region_items(self):
        """Iterate over all (address, bytearray) pairs."""
        return self._regions.items()

    def region_keys(self):
        """Iterate over all region addresses."""
        return self._regions.keys()

    def region_count(self) -> int:
        """Number of regions."""
        return len(self._regions)

    def heap_count(self) -> int:
        """Number of heap objects."""
        return len(self._heap)

    def heap_values(self):
        """Iterate over all HeapObjects."""
        return self._heap.values()

    def fresh_symbolic(self, hint: str = "") -> SymbolicValue:
        name = f"sym_{self.symbolic_counter}"
        self.symbolic_counter += 1
        return SymbolicValue(name=name, type_hint=hint or None)

    @property
    def current_frame(self) -> StackFrame:
        return self.call_stack[-1]

    def to_dict(self) -> dict:
        result: dict[str, Any] = {
            "heap": {str(k): v.to_dict() for k, v in self._heap.items()},
            "call_stack": [f.to_dict() for f in self.call_stack],
            "path_conditions": self.path_conditions,
            "symbolic_counter": self.symbolic_counter,
        }
        if self.closures:
            result["closures"] = {
                label: env.to_dict() for label, env in self.closures.items()
            }
        if self._regions:
            result["regions"] = {
                str(addr): list(data) for addr, data in self._regions.items()
            }
        if self.continuations:
            result["continuations"] = {k: str(v) for k, v in self.continuations.items()}
        if self.data_layout:
            result["data_layout"] = dict(self.data_layout)
        return result


# ── StateUpdate schema (LLM output) ─────────────────────────────


class HeapWrite(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    obj_addr: Address
    field: FieldName
    value: Any


class NewObject(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    addr: Address
    type_hint: TypeExpr = UNKNOWN


class RegionWrite(BaseModel):
    region_addr: Address
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
    function_name: FuncName
    return_label: CodeLabel | None = None
    closure_env_id: str = ""
    captured_var_names: list[VarName] = []
    is_ctor: bool = False


VOID_RETURN: TypedValue = typed(None, scalar(TypeName.VOID))


class StateUpdate(BaseModel):
    register_writes: dict[Register, Any] = {}
    var_writes: dict[VarName, Any] = {}
    heap_writes: list[HeapWrite] = []
    new_objects: list[NewObject] = []
    region_writes: list[RegionWrite] = []
    new_regions: dict[str, int] = {}
    continuation_writes: dict[str, CodeLabel] = {}
    continuation_clear: str = ""
    next_label: CodeLabel | None = None
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
