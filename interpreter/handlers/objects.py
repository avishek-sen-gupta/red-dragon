"""Object creation opcode handlers: NEW_OBJECT, NEW_ARRAY."""

from __future__ import annotations

from typing import Any

from interpreter.instructions import InstructionBase, NewObject as NewObjectInst
from interpreter.instructions import NewArray
from interpreter.vm.vm import (
    VMState,
    Pointer,
    ExecutionResult,
    StateUpdate,
    NewObject,
)
from interpreter.refs.class_ref import ClassRef
from interpreter.types.type_expr import TypeExpr, pointer, scalar
from interpreter.types.typed_value import typed
from interpreter.address import Address
from interpreter import constants
from interpreter.var_name import VarName


def _handle_new_object(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, NewObjectInst)
    obj_type = (
        t.type_hint
        if isinstance(t.type_hint, TypeExpr) and t.type_hint
        else scalar(str(t.type_hint)) if t.type_hint else scalar("Object")
    )
    # Dereference: if type_hint names a variable holding a ClassRef,
    # extract the canonical class name.
    hint_name = str(obj_type)
    for frame in reversed(vm.call_stack):
        if VarName(hint_name) in frame.local_vars:
            raw = frame.local_vars[VarName(hint_name)].value
            if isinstance(raw, ClassRef):
                obj_type = scalar(raw.name)
            break
    addr = f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    if not obj_type:
        obj_type = scalar("Object")
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=Address(addr), type_hint=obj_type)],
            register_writes={
                t.result_reg: typed(
                    Pointer(base=Address(addr), offset=0),
                    pointer(obj_type),
                )
            },
            reasoning=f"new {obj_type} → {addr}",
        )
    )


def _handle_new_array(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, NewArray)
    addr = f"{constants.ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    arr_type = (
        t.type_hint
        if isinstance(t.type_hint, TypeExpr) and t.type_hint
        else scalar(str(t.type_hint)) if t.type_hint else scalar("Array")
    )
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=Address(addr), type_hint=arr_type)],
            register_writes={
                t.result_reg: typed(
                    Pointer(base=Address(addr), offset=0),
                    pointer(arr_type),
                )
            },
            reasoning=f"new {arr_type}[] → {addr}",
        )
    )
