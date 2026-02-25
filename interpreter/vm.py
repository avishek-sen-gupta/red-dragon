"""Symbolic VM — data types, state update application, and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .ir import IRInstruction, Opcode

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
class StackFrame:
    function_name: str
    registers: dict[str, Any] = field(default_factory=dict)
    local_vars: dict[str, Any] = field(default_factory=dict)
    return_label: str | None = None
    return_ip: int | None = None  # ip to resume at in caller block
    result_reg: str | None = None  # caller's register for return value

    def to_dict(self) -> dict:
        return {
            "function_name": self.function_name,
            "registers": {k: _serialize_value(v) for k, v in self.registers.items()},
            "local_vars": {k: _serialize_value(v) for k, v in self.local_vars.items()},
            "return_label": self.return_label,
        }


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

    def fresh_symbolic(self, hint: str = "") -> SymbolicValue:
        name = f"sym_{self.symbolic_counter}"
        self.symbolic_counter += 1
        return SymbolicValue(name=name, type_hint=hint or None)

    @property
    def current_frame(self) -> StackFrame:
        return self.call_stack[-1]

    def to_dict(self) -> dict:
        return {
            "heap": {k: v.to_dict() for k, v in self.heap.items()},
            "call_stack": [f.to_dict() for f in self.call_stack],
            "path_conditions": self.path_conditions,
            "symbolic_counter": self.symbolic_counter,
        }


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


def apply_update(vm: VMState, update: StateUpdate):
    """Mechanically apply a StateUpdate to the VM."""
    frame = vm.current_frame

    # New objects
    for obj in update.new_objects:
        vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

    # Register writes — always to the CURRENT (caller's) frame
    for reg, val in update.register_writes.items():
        frame.registers[reg] = _deserialize_value(val, vm)

    # Heap writes
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        vm.heap[hw.obj_addr].fields[hw.field] = _deserialize_value(hw.value, vm)

    # Path condition
    if update.path_condition:
        vm.path_conditions.append(update.path_condition)

    # Call push — push BEFORE var_writes so parameter bindings go to the
    # new frame when dispatching a function call
    if update.call_push:
        vm.call_stack.append(
            StackFrame(
                function_name=update.call_push.function_name,
                return_label=update.call_push.return_label,
            )
        )

    # Variable writes — go to the CURRENT frame (which is the new frame
    # if call_push just fired, i.e. parameter bindings)
    target_frame = vm.current_frame
    for var, val in update.var_writes.items():
        target_frame.local_vars[var] = _deserialize_value(val, vm)

    # Call pop
    if update.call_pop and len(vm.call_stack) > 1:
        vm.call_stack.pop()


def _deserialize_value(val: Any, vm: VMState) -> Any:
    """Convert a dict with __symbolic__ into a SymbolicValue."""
    if isinstance(val, dict) and val.get("__symbolic__"):
        return SymbolicValue(
            name=val.get("name", f"sym_{vm.symbolic_counter}"),
            type_hint=val.get("type_hint"),
            constraints=val.get("constraints", []),
        )
    return val


# ── Helpers ──────────────────────────────────────────────────────


def _is_symbolic(val: Any) -> bool:
    return isinstance(val, SymbolicValue)


def _heap_addr(val: Any) -> str:
    """Extract a heap address from a value.

    Values can be plain strings ("obj_Point_1") or dicts with an addr key
    ({"addr": "obj_Point_1", "type_hint": "Point"}) — the latter is what
    the LLM returns for constructor calls.  Returns empty string if val
    doesn't reference a heap address.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, dict) and "addr" in val:
        return val["addr"]
    return ""


def _resolve_reg(vm: VMState, operand: str) -> Any:
    """Resolve a register name to its value, or return the operand as-is."""
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        return frame.registers.get(operand, operand)
    return operand


def _parse_const(raw: str) -> Any:
    """Parse a constant literal string into a Python value."""
    if raw == "None":
        return None
    if raw == "True":
        return True
    if raw == "False":
        return False
    try:
        return int(raw)
    except (ValueError, TypeError):
        pass
    try:
        return float(raw)
    except (ValueError, TypeError):
        pass
    # String literal — strip quotes if present
    if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


class Operators:
    """Binary and unary operator evaluation with an explicit UNCOMPUTABLE sentinel."""

    class _Uncomputable:
        """Sentinel value indicating an operation could not be computed."""

        def __repr__(self) -> str:
            return "UNCOMPUTABLE"

    UNCOMPUTABLE = _Uncomputable()

    BINOP_TABLE: dict[str, Any] = {
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
        "/": lambda a, b: a / b if b != 0 else Operators.UNCOMPUTABLE,
        "//": lambda a, b: a // b if b != 0 else Operators.UNCOMPUTABLE,
        "%": lambda a, b: a % b if b != 0 else Operators.UNCOMPUTABLE,
        "**": lambda a, b: a**b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        ">=": lambda a, b: a >= b,
        "and": lambda a, b: a and b,
        "or": lambda a, b: a or b,
        "in": lambda a, b: (
            a in b if hasattr(b, "__contains__") else Operators.UNCOMPUTABLE
        ),
        "&": lambda a, b: a & b,
        "|": lambda a, b: a | b,
        "^": lambda a, b: a ^ b,
        "<<": lambda a, b: a << b,
        ">>": lambda a, b: a >> b,
    }

    @classmethod
    def eval_binop(cls, op: str, lhs: Any, rhs: Any) -> Any:
        fn = cls.BINOP_TABLE.get(op)
        if fn is None:
            return cls.UNCOMPUTABLE
        try:
            return fn(lhs, rhs)
        except Exception:
            return cls.UNCOMPUTABLE

    @classmethod
    def eval_unop(cls, op: str, operand: Any) -> Any:
        try:
            if op == "-":
                return -operand
            if op == "+":
                return +operand
            if op == "not":
                return not operand
            if op == "~":
                return ~operand
        except Exception:
            pass
        return cls.UNCOMPUTABLE
