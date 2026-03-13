"""Symbolic VM — state update application and helpers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from interpreter.constants import CanonicalLiteral, TypeName
from interpreter.conversion_rules import TypeConversionRules
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.type_environment import TypeEnvironment
from interpreter.type_expr import UNKNOWN, ScalarType, scalar
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
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
    VOID_RETURN,
)

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
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
    rt_type_name = runtime_type_name(val)
    if not rt_type_name or rt_type_name == target_type:
        return val
    coercer = conversion_rules.coerce_assignment(scalar(rt_type_name), target_type)
    return coercer(val)


def _materialize_single_register(
    val: Any,
    vm: VMState,
    reg: str,
    type_env: TypeEnvironment,
    conversion_rules: TypeConversionRules,
) -> TypedValue:
    """Deserialize, coerce, and wrap a single register value as TypedValue."""
    deserialized = _deserialize_value(val, vm)
    coerced = _coerce_value(deserialized, reg, type_env, conversion_rules)
    declared_type = type_env.register_types.get(reg, UNKNOWN)
    inferred_type = declared_type or typed_from_runtime(coerced).type
    return typed(coerced, inferred_type)


def _materialize_single_var(
    val: Any,
    vm: VMState,
    var: str,
    type_env: TypeEnvironment,
) -> TypedValue:
    """Deserialize and wrap a single variable value as TypedValue (no register coercion)."""
    deserialized = _deserialize_value(val, vm)
    declared_type = type_env.var_types.get(var, UNKNOWN)
    inferred_type = declared_type or typed_from_runtime(deserialized).type
    return typed(deserialized, inferred_type)


def _coerce_typed_register(
    tv: TypedValue,
    reg: str,
    type_env: TypeEnvironment,
    conversion_rules: TypeConversionRules,
) -> TypedValue:
    """Coerce a handler-produced TypedValue's raw value to match its declared type.

    Handles the case where Python produces a float (e.g. 4/2 → 2.0) but the
    inferred type is Int — the raw value must be coerced so downstream consumers
    (STORE_INDEX, etc.) see the correct Python type.
    """
    target_type = type_env.register_types.get(reg, tv.type)
    if not target_type:
        return tv
    rt_type_name = runtime_type_name(tv.value)
    if not rt_type_name or rt_type_name == (
        target_type.name if isinstance(target_type, ScalarType) else ""
    ):
        return tv
    coercer = conversion_rules.coerce_assignment(scalar(rt_type_name), target_type)
    coerced = coercer(tv.value)
    return typed(coerced, target_type) if coerced is not tv.value else tv


def coerce_local_update(
    update: StateUpdate,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
) -> StateUpdate:
    """Coerce register writes in a handler-produced StateUpdate to declared types.

    Unlike materialize_raw_update, this assumes all values are already TypedValue
    (produced by local handlers) and only applies type coercion — no deserialization.
    """
    coerced_reg_writes = {
        reg: _coerce_typed_register(val, reg, type_env, conversion_rules)
        for reg, val in update.register_writes.items()
        if isinstance(val, TypedValue)
    }
    uncoerced_reg_writes = {
        reg: val
        for reg, val in update.register_writes.items()
        if not isinstance(val, TypedValue)
    }
    return update.model_copy(
        update={"register_writes": {**uncoerced_reg_writes, **coerced_reg_writes}}
    )


def materialize_raw_update(
    raw_update: StateUpdate,
    vm: VMState,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
) -> StateUpdate:
    """Transform a raw StateUpdate (from LLM) into one with TypedValue values.

    Already-wrapped TypedValue entries are coerced to match declared types.
    Register values get deserialized, coerced, and wrapped.
    Variable values get deserialized and wrapped (no register coercion).
    """
    typed_reg_writes = {
        reg: (
            _coerce_typed_register(val, reg, type_env, conversion_rules)
            if isinstance(val, TypedValue)
            else _materialize_single_register(val, vm, reg, type_env, conversion_rules)
        )
        for reg, val in raw_update.register_writes.items()
    }
    typed_var_writes = {
        var: (
            val
            if isinstance(val, TypedValue)
            else _materialize_single_var(val, vm, var, type_env)
        )
        for var, val in raw_update.var_writes.items()
    }
    materialized_rv = raw_update.return_value
    if isinstance(raw_update.return_value, TypedValue):
        materialized_rv = raw_update.return_value
    elif raw_update.return_value is None:
        materialized_rv = VOID_RETURN
    else:
        deserialized = _deserialize_value(raw_update.return_value, vm)
        materialized_rv = typed_from_runtime(deserialized)

    typed_heap_writes = [
        HeapWrite(
            obj_addr=hw.obj_addr,
            field=hw.field,
            value=(
                hw.value
                if isinstance(hw.value, TypedValue)
                else typed_from_runtime(_deserialize_value(hw.value, vm))
            ),
        )
        for hw in raw_update.heap_writes
    ]

    return raw_update.model_copy(
        update={
            "register_writes": typed_reg_writes,
            "var_writes": typed_var_writes,
            "return_value": materialized_rv,
            "heap_writes": typed_heap_writes,
        }
    )


def apply_update(
    vm: VMState,
    update: StateUpdate,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
):
    """Mechanically apply a StateUpdate to the VM.

    Expects register_writes and var_writes to contain TypedValue entries
    (via materialize_raw_update). Raw values are auto-materialized as a
    transition measure — tests and other direct callers may pass raw values
    until all handlers produce TypedValue (tracked in red-dragon-rrb).
    """
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

    # Register writes — auto-materialize raw values (transition), then coerce
    for reg, val in update.register_writes.items():
        tv = (
            val
            if isinstance(val, TypedValue)
            else _materialize_single_register(val, vm, reg, type_env, conversion_rules)
        )
        declared = type_env.register_types.get(reg, UNKNOWN)
        if declared and tv.type != declared:
            coerced = _coerce_value(tv.value, reg, type_env, conversion_rules)
            frame.registers[reg] = typed(coerced, declared)
        else:
            frame.registers[reg] = tv

    # Heap writes — store TypedValue directly (Phase 2)
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        val = (
            hw.value
            if isinstance(hw.value, TypedValue)
            else typed_from_runtime(_deserialize_value(hw.value, vm))
        )
        vm.heap[hw.obj_addr].fields[hw.field] = val

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
                is_ctor=update.call_push.is_ctor,
            )
        )

    # Variable writes — go to the CURRENT frame (which is the new frame
    # if call_push just fired, i.e. parameter bindings)
    target_frame = vm.current_frame
    for var, val in update.var_writes.items():
        tv = (
            val
            if isinstance(val, TypedValue)
            else _materialize_single_var(val, vm, var, type_env)
        )
        raw_val = tv.value
        # Alias-aware: if variable is backed by a heap object, write TypedValue
        alias_ptr = target_frame.var_heap_aliases.get(var)
        if alias_ptr and alias_ptr.base in vm.heap:
            vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = tv
        else:
            target_frame.local_vars[var] = tv
        if target_frame.closure_env_id and var in target_frame.captured_var_names:
            env = vm.closures.get(target_frame.closure_env_id)
            if env:
                # Closure bindings stay raw
                env.bindings[var] = raw_val

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
    """Resolve a register name to its raw value, or return the operand as-is.

    Unwraps TypedValue automatically so existing handlers work unchanged.
    """
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val.value
        return val
    return operand


def _resolve_binop_operand(vm: VMState, operand: str) -> TypedValue:
    """Resolve a register name to its TypedValue.

    Used by type-aware handlers (BINOP). Falls back to typed_from_runtime
    if the operand is not a register or not wrapped.
    """
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val
        return typed_from_runtime(val)
    return typed_from_runtime(operand)


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


from interpreter.typed_value import runtime_type_name  # noqa: F401 — re-exported


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
        "~": lambda a, b: a ^ b,  # Lua bitwise XOR
        "<<": lambda a, b: a << b,
        ">>": lambda a, b: a >> b,
        "..": lambda a, b: str(a) + str(b),
        ".": lambda a, b: str(a) + str(b),
        "===": lambda a, b: a == b,
        "?:": lambda a, b: a if a is not None else b,
        "||": lambda a, b: a or b,
        "&&": lambda a, b: a and b,
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
