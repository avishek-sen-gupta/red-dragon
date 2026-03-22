"""Shared helpers used by multiple handler families."""

from __future__ import annotations

from typing import Any

from interpreter.vm import VMState, SymbolicValue, _heap_addr, _is_symbolic
from interpreter.vm_types import StackFrame
from interpreter.types.type_expr import UNKNOWN, TypeExpr, scalar
from interpreter.types.typed_value import TypedValue, typed
from interpreter.ir import SpreadArguments


def _resolve_call_args(vm: VMState, arg_operands: list) -> list[TypedValue]:
    """Resolve call arguments, expanding SpreadArguments from the heap."""
    from interpreter.vm import _resolve_reg

    args: list[TypedValue] = []
    for op in arg_operands:
        if isinstance(op, SpreadArguments):
            tv = _resolve_reg(vm, op.register)
            addr = _heap_addr(tv.value)
            if addr and addr in vm.heap:
                fields = vm.heap[addr].fields
                args.extend(
                    fields[str(i)] for i in range(len(fields)) if str(i) in fields
                )
            else:
                args.append(tv)
        else:
            args.append(_resolve_reg(vm, op))
    return args


def _symbolic_name(val: Any) -> str:
    """Get a human-readable name for a value, suitable for symbolic hints."""
    if isinstance(val, SymbolicValue):
        return val.name
    if isinstance(val, dict) and val.get("__symbolic__"):
        return val.get("name", "?")
    return repr(val)


def _symbolic_type_hint(val: Any) -> TypeExpr:
    """Extract a type hint from a symbolic value (SymbolicValue or dict)."""
    if isinstance(val, SymbolicValue):
        return scalar(val.type_hint) if val.type_hint else UNKNOWN
    if isinstance(val, dict) and val.get("__symbolic__"):
        hint = val.get("type_hint", "")
        return scalar(hint) if hint else UNKNOWN
    return UNKNOWN


def _write_var_to_frame(
    vm: VMState, frame: StackFrame, name: str, tv: TypedValue
) -> None:
    """Write a variable to a specific frame, handling aliases and closure envs."""
    alias_ptr = frame.var_heap_aliases.get(name)
    if alias_ptr and alias_ptr.base in vm.heap:
        vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = tv
    else:
        frame.local_vars[name] = tv
    if frame.closure_env_id and name in frame.captured_var_names:
        env = vm.closures.get(frame.closure_env_id)
        if env:
            env.bindings[name] = tv
