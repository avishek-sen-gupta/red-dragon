"""Symbolic VM — data types (pure data, no business logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

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


@dataclass
class HeapObject:
    type_hint: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type_hint": self.type_hint,
            "fields": {k: _serialize_value(v) for k, v in self.fields.items()},
        }


@dataclass
class ClosureEnvironment:
    """Shared mutable environment for closure capture-by-reference."""

    bindings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: _serialize_value(v) for k, v in self.bindings.items()}


@dataclass
class StackFrame:
    function_name: str
    registers: dict[str, Any] = field(default_factory=dict)
    local_vars: dict[str, Any] = field(default_factory=dict)
    return_label: str | None = None
    return_ip: int | None = None  # ip to resume at in caller block
    result_reg: str | None = None  # caller's register for return value
    closure_env_id: str = ""
    captured_var_names: frozenset[str] = field(default_factory=frozenset)

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
    if isinstance(v, SymbolicValue):
        return v.to_dict()
    if isinstance(v, HeapObject):
        return v.to_dict()
    return v


@dataclass
class VMState:
    heap: dict[str, HeapObject] = field(default_factory=dict)
    call_stack: list[StackFrame] = field(default_factory=list)
    path_conditions: list[str] = field(default_factory=list)
    symbolic_counter: int = 0
    closures: dict[str, ClosureEnvironment] = field(default_factory=dict)

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
        return result


# ── StateUpdate schema (LLM output) ─────────────────────────────


class HeapWrite(BaseModel):
    obj_addr: str
    field: str
    value: Any


class NewObject(BaseModel):
    addr: str
    type_hint: str | None = None


class StackFramePush(BaseModel):
    function_name: str
    return_label: str | None = None
    closure_env_id: str = ""
    captured_var_names: list[str] = []


class StateUpdate(BaseModel):
    register_writes: dict[str, Any] = {}
    var_writes: dict[str, Any] = {}
    heap_writes: list[HeapWrite] = []
    new_objects: list[NewObject] = []
    next_label: str | None = None
    call_push: StackFramePush | None = None
    call_pop: bool = False
    return_value: Any | None = None
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
