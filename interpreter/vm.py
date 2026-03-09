"""Symbolic VM — state update application and helpers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from interpreter.constants import CanonicalLiteral, TypeName
from interpreter.conversion_rules import TypeConversionRules
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.type_environment import TypeEnvironment
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.vm_types import (  # noqa: F401 — re-exported for backwards compatibility
    SymbolicValue,
    HeapObject,
    ClosureEnvironment,
    ExceptionHandler,
    Pointer,
    StackFrame,
    VMState,
    HeapWrite,
    NewObject,
    RegionWrite,
    StackFramePush,
    StateUpdate,
    ExecutionResult,
    _serialize_value,
)

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
    func_signatures=MappingProxyType({}),
)

_IDENTITY_RULES = IdentityConversionRules()


def _coerce_value(
    val: Any,
    reg: str,
    type_env: TypeEnvironment,
    conversion_rules: TypeConversionRules,
) -> Any:
    """Coerce *val* to the type declared for *reg* in *type_env*.

    Returns *val* unchanged when no coercion is needed (no declared type,
    runtime type already matches, or the register name is not in the env).
    """
    if not isinstance(reg, str) or not reg.startswith("%"):
        return val
    target_type = type_env.register_types.get(reg, UNKNOWN)
    if not target_type:
        return val
    runtime_type_name = _runtime_type_name(val)
    if not runtime_type_name or runtime_type_name == target_type:
        return val
    coercer = conversion_rules.coerce_assignment(scalar(runtime_type_name), target_type)
    return coercer(val)


def apply_update(
    vm: VMState,
    update: StateUpdate,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
):
    """Mechanically apply a StateUpdate to the VM."""
    frame = vm.current_frame

    # New regions
    for addr, size in update.new_regions.items():
        vm.regions[addr] = bytearray(size)

    # Region writes
    for rw in update.region_writes:
        vm.regions[rw.region_addr][rw.offset : rw.offset + len(rw.data)] = bytes(
            rw.data
        )

    # Continuation writes
    for name, label in update.continuation_writes.items():
        vm.continuations[name] = label

    # Continuation clear (fired by RESUME_CONTINUATION)
    if update.continuation_clear:
        vm.continuations.pop(update.continuation_clear, None)

    # New objects
    for obj in update.new_objects:
        vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

    # Register writes — always to the CURRENT (caller's) frame
    # Coerce values at write time based on the type environment.
    for reg, val in update.register_writes.items():
        deserialized = _deserialize_value(val, vm)
        frame.registers[reg] = _coerce_value(
            deserialized, reg, type_env, conversion_rules
        )

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
                closure_env_id=update.call_push.closure_env_id,
                captured_var_names=frozenset(update.call_push.captured_var_names),
            )
        )

    # Variable writes — go to the CURRENT frame (which is the new frame
    # if call_push just fired, i.e. parameter bindings)
    target_frame = vm.current_frame
    for var, val in update.var_writes.items():
        deserialized = _deserialize_value(val, vm)
        # Alias-aware: if variable is backed by a heap object, write there
        alias_ptr = target_frame.var_heap_aliases.get(var)
        if alias_ptr and alias_ptr.base in vm.heap:
            vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = deserialized
        else:
            target_frame.local_vars[var] = deserialized
        if target_frame.closure_env_id and var in target_frame.captured_var_names:
            env = vm.closures.get(target_frame.closure_env_id)
            if env:
                env.bindings[var] = deserialized

    # Call pop
    if update.call_pop and len(vm.call_stack) > 1:
        vm.call_stack.pop()


def _deserialize_value(val: Any, vm: VMState) -> Any:
    """Convert a dict with __symbolic__ or __pointer__ into typed objects."""
    if isinstance(val, dict) and val.get("__symbolic__"):
        return SymbolicValue(
            name=val.get("name", f"sym_{vm.symbolic_counter}"),
            type_hint=val.get("type_hint"),
            constraints=val.get("constraints", []),
        )
    if isinstance(val, dict) and val.get("__pointer__"):
        return Pointer(base=val["base"], offset=val.get("offset", 0))
    return val


# ── Helpers ──────────────────────────────────────────────────────


def _is_symbolic(val: Any) -> bool:
    return isinstance(val, SymbolicValue)


def _heap_addr(val: Any) -> str:
    """Extract a heap address from a value.

    Values can be plain strings ("obj_Point_1") or dicts with an addr key
    ({"addr": "obj_Point_1", "type_hint": "Point"}) — the latter is what
    the LLM returns for constructor calls.  Symbolic value dicts use their
    name as the heap address (for materialised symbolic heap entries).
    Returns empty string if val doesn't reference a heap address.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, SymbolicValue):
        return val.name
    if isinstance(val, dict):
        if "addr" in val:
            return val["addr"]
        if val.get("__symbolic__") and "name" in val:
            return val["name"]
    return ""


def _resolve_reg(vm: VMState, operand: str) -> Any:
    """Resolve a register name to its value, or return the operand as-is."""
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        return frame.registers.get(operand, operand)
    return operand


def _parse_const(raw: str) -> Any:
    """Parse a constant literal string into a Python value."""
    if raw == CanonicalLiteral.NONE:
        return None
    if raw == CanonicalLiteral.TRUE:
        return True
    if raw == CanonicalLiteral.FALSE:
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


_PYTHON_TYPE_TO_TYPE_NAME: dict[type, str] = {
    bool: TypeName.BOOL,
    int: TypeName.INT,
    float: TypeName.FLOAT,
    str: TypeName.STRING,
}


def _runtime_type_name(val: Any) -> str:
    """Map a Python runtime value to its canonical TypeName.

    bool must be checked before int because ``isinstance(True, int)`` is True.
    Returns empty string for unrecognised types (no coercion will be applied).
    """
    # Exact type lookup avoids isinstance chains and the bool/int subclass trap.
    return _PYTHON_TYPE_TO_TYPE_NAME.get(type(val), "")


def _resolve_typed_reg(
    vm: VMState,
    operand: str,
    type_env: TypeEnvironment,
    conversion_rules: TypeConversionRules,
) -> Any:
    """Resolve a register value and coerce it to the type declared by *type_env*.

    Falls back to plain ``_resolve_reg`` when the operand is not a register,
    has no declared type, or the runtime type already matches.
    """
    val = _resolve_reg(vm, operand)
    return _coerce_value(val, operand, type_env, conversion_rules)


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
        "mod": lambda a, b: a % b if b != 0 else Operators.UNCOMPUTABLE,
        "**": lambda a, b: a**b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "~=": lambda a, b: a != b,
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
        "..": lambda a, b: str(a) + str(b),
        ".": lambda a, b: str(a) + str(b),
        "===": lambda a, b: a == b,
        "?:": lambda a, b: a if a is not None else b,
    }

    @classmethod
    def eval_binop(cls, op: str, lhs: Any, rhs: Any) -> Any:
        fn = cls.BINOP_TABLE.get(op)
        if fn is None:
            return cls.UNCOMPUTABLE
        try:
            return fn(lhs, rhs)
        except (TypeError, ArithmeticError, AttributeError):
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
            if op == "#":
                return len(operand)
            if op == "!":
                return not operand
            if op == "!!":
                return operand
        except (TypeError, ArithmeticError, AttributeError):
            pass
        return cls.UNCOMPUTABLE
