"""Object creation opcode handlers: NEW_OBJECT, NEW_ARRAY."""

from __future__ import annotations

from typing import Any

from interpreter.ir import IRInstruction
from interpreter.vm.vm import (
    VMState,
    Pointer,
    ExecutionResult,
    StateUpdate,
    NewObject,
)
from interpreter.refs.class_ref import ClassRef
from interpreter.types.type_expr import pointer, scalar
from interpreter.types.typed_value import typed
from interpreter import constants


def _handle_new_object(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    type_hint = inst.operands[0] if inst.operands else ""
    # Dereference: if type_hint is a variable holding a ClassRef,
    # extract the canonical class name (e.g. Foo → __anon_class_0).
    for frame in reversed(vm.call_stack):
        if type_hint in frame.local_vars:
            raw = frame.local_vars[type_hint].value
            if isinstance(raw, ClassRef):
                type_hint = raw.name
            break
    addr = f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    obj_type = scalar(type_hint or "Object")
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=obj_type)],
            register_writes={
                inst.result_reg: typed(
                    Pointer(base=addr, offset=0),
                    pointer(obj_type),
                )
            },
            reasoning=f"new {type_hint} → {addr}",
        )
    )


def _handle_new_array(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    type_hint = inst.operands[0] if inst.operands else ""
    addr = f"{constants.ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    arr_type = scalar(type_hint or "Array")
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=arr_type)],
            register_writes={
                inst.result_reg: typed(
                    Pointer(base=addr, offset=0),
                    pointer(arr_type),
                )
            },
            reasoning=f"new {type_hint}[] → {addr}",
        )
    )
