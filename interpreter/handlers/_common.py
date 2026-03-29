"""Shared helpers used by multiple handler families."""

from __future__ import annotations

from typing import Any

from interpreter.address import Address
from interpreter.vm.vm import VMState, SymbolicValue, _heap_addr, _is_symbolic
from interpreter.vm.vm_types import StackFrame
from interpreter.field_name import FieldName, FieldKind
from interpreter.types.type_expr import UNKNOWN, TypeExpr, scalar
from interpreter.types.typed_value import TypedValue, typed
from interpreter.ir import SpreadArguments
from interpreter.var_name import VarName


def _resolve_call_args(vm: VMState, arg_operands: list) -> list[TypedValue]:
    """Resolve call arguments, expanding SpreadArguments from the heap."""
    from interpreter.vm.vm import _resolve_reg

    args: list[TypedValue] = []
    for op in arg_operands:
        if isinstance(op, SpreadArguments):
            tv = _resolve_reg(vm, op.register)
            addr = _heap_addr(tv.value)
            if addr and vm.heap_contains(addr):
                fields = vm.heap_get(addr).fields
                args.extend(
                    fields[FieldName(str(i), FieldKind.INDEX)]
                    for i in range(len(fields))
                    if FieldName(str(i), FieldKind.INDEX) in fields
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
    vm: VMState, frame: StackFrame, name: VarName, tv: TypedValue
) -> None:
    """Write a variable to a specific frame, handling aliases and closure envs."""
    alias_ptr = frame.var_heap_aliases.get(name)
    if alias_ptr and vm.heap_contains(Address(alias_ptr.base)):
        vm.heap_get(Address(alias_ptr.base)).fields[
            FieldName(str(alias_ptr.offset), FieldKind.INDEX)
        ] = tv
    else:
        frame.local_vars[name] = tv
    if frame.closure_env_id and name in frame.captured_var_names:
        env = vm.closures.get(frame.closure_env_id)
        if env:
            env.bindings[name] = tv
