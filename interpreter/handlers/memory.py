"""Memory-related opcode handlers: LOAD_FIELD, STORE_FIELD, LOAD_INDEX, STORE_INDEX,
LOAD_INDIRECT, STORE_INDIRECT, ADDRESS_OF, LOAD_FIELD_INDIRECT."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.instructions import (
    InstructionBase,
    AddressOf,
    LoadIndirect,
    LoadFieldIndirect,
    StoreIndirect,
    StoreField,
    LoadField,
    StoreIndex,
    LoadIndex,
)
from interpreter.address import Address
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.vm.vm import (
    VMState,
    HeapObject,
    Pointer,
    ExecutionResult,
    StateUpdate,
    _resolve_reg,
    _heap_addr,
    _is_symbolic,
    _parse_const,
)
from interpreter.vm.vm_types import HeapWrite
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.field_name import FieldName, FieldKind
from interpreter import constants
from interpreter.handlers._common import _symbolic_name, _symbolic_type_hint

logger = logging.getLogger(__name__)


def _infer_index_kind(idx_val: Any) -> FieldKind:
    """Determine whether an index value represents a numeric index or a named property.

    Numeric indices (int or string representation of a non-negative integer)
    use INDEX kind; everything else uses PROPERTY kind.
    """
    if isinstance(idx_val, int):
        return FieldKind.INDEX
    if isinstance(idx_val, str):
        try:
            int(idx_val)
            return FieldKind.INDEX
        except ValueError:
            pass
    return FieldKind.PROPERTY


def _find_method_missing(
    heap_obj: HeapObject,
    registry: FunctionRegistry,
    cfg: CFG,
) -> BoundFuncRef | None:
    """Look up __method_missing__ on a heap object: instance field first, then class registry."""
    if FieldName(constants.METHOD_MISSING) in heap_obj.fields:
        mm_tv = heap_obj.fields[FieldName(constants.METHOD_MISSING)]
        if isinstance(mm_tv.value, BoundFuncRef):
            return mm_tv.value
    # Check class-level __method_missing__ via registry
    type_name = str(heap_obj.type_hint) if heap_obj.type_hint else ""
    mm_labels = registry.lookup_methods(
        ClassName(type_name), FuncName(constants.METHOD_MISSING)
    )
    if mm_labels and mm_labels[0] in cfg.blocks:
        return BoundFuncRef(
            func_ref=FuncRef(
                name=FuncName(constants.METHOD_MISSING), label=mm_labels[0]
            ),
        )
    return None


def _resolve_method_delegation_target(
    addr: "Address",
    method_name: FuncName,
    vm: VMState,
    registry: FunctionRegistry,
    cfg: CFG,
) -> tuple["Address", TypedValue] | None:
    """Follow __boxed__ delegation chain to find an inner object that owns *method_name*.

    Returns (inner_addr, inner_typed_value) for the first object whose type
    has *method_name* in the class method registry, or None if the chain is
    exhausted without finding one.
    """
    current_addr = addr
    visited: set["Address"] = set()
    while (
        current_addr and vm.heap_contains(current_addr) and current_addr not in visited
    ):
        visited.add(current_addr)
        heap_obj = vm.heap_get(current_addr)
        # Only follow delegation if this object has __method_missing__
        if _find_method_missing(heap_obj, registry, cfg) is None:
            return None
        # Follow the __boxed__ field to the inner object
        if FieldName(constants.BOXED_FIELD) not in heap_obj.fields:
            return None
        inner_tv = heap_obj.fields[FieldName(constants.BOXED_FIELD)]
        inner_addr = _heap_addr(inner_tv.value)
        if not inner_addr or not vm.heap_contains(inner_addr):
            return None
        inner_type = str(vm.heap_get(inner_addr).type_hint or "")
        if registry.lookup_methods(ClassName(inner_type), method_name):
            return (inner_addr, inner_tv)
        # Inner object might itself be a Box — continue the chain
        current_addr = inner_addr
    return None


def _handle_address_of(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    """ADDRESS_OF var_name: promote variable to heap and return a Pointer."""
    t = inst
    assert isinstance(t, AddressOf)
    name = t.var_name
    frame = vm.current_frame

    # Already aliased — return the existing Pointer
    if name in frame.var_heap_aliases:
        ptr = frame.var_heap_aliases[name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={
                    t.result_reg: typed(ptr, scalar(constants.TypeName.POINTER))
                },
                reasoning=f"address_of {name} → {ptr} (already aliased)",
            )
        )

    # Look up the variable's current value across the call stack
    current_val = None
    for f in reversed(vm.call_stack):
        if name in f.local_vars:
            current_val = f.local_vars[name].value
            break

    # Function reference: &func_name returns the reference unchanged
    # (identity semantics — our model already uses references for functions)
    if isinstance(current_val, BoundFuncRef):
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed_from_runtime(current_val)},
                reasoning=f"address_of {name} → {current_val} (function ref, identity)",
            )
        )

    # If variable holds a bare heap address string or a Pointer from NEW_OBJECT /
    # NEW_ARRAY (base starts with obj_ or arr_ prefix), return identity — the
    # object is already on the heap. Pointer values from ADDRESS_OF (base starts
    # with mem_) need double-indirection: promote the Pointer itself to a new heap slot.
    is_heap_pointer = isinstance(current_val, Pointer) and (
        current_val.base.startswith(constants.OBJ_ADDR_PREFIX)
        or current_val.base.startswith(constants.ARR_ADDR_PREFIX)
    )
    addr = (
        _heap_addr(current_val)
        if not isinstance(current_val, Pointer) or is_heap_pointer
        else ""
    )
    if addr and vm.heap_contains(addr):
        ptr = Pointer(base=addr, offset=0)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={
                    t.result_reg: typed(ptr, scalar(constants.TypeName.POINTER))
                },
                reasoning=f"address_of {name} → {ptr} (existing heap object)",
            )
        )

    # Promote primitive to heap: allocate a HeapObject with field "0"
    mem_addr = f"mem_{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    vm.heap_set(
        Address(mem_addr),
        HeapObject(
            type_hint=None,
            fields={FieldName("0", FieldKind.INDEX): typed_from_runtime(current_val)},
        ),
    )
    ptr = Pointer(base=Address(mem_addr), offset=0)
    frame.var_heap_aliases[name] = ptr
    logger.debug("address_of: promoted %s=%r to heap %s", name, current_val, mem_addr)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={
                t.result_reg: typed(ptr, scalar(constants.TypeName.POINTER))
            },
            reasoning=f"address_of {name} → {ptr} (promoted to heap {mem_addr})",
        )
    )


def _handle_load_indirect(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    """LOAD_INDIRECT %ptr: read through a Pointer (dereference)."""
    t = inst
    assert isinstance(t, LoadIndirect)
    obj_val = _resolve_reg(vm, t.ptr_reg).value
    # Pointer dereference: read from heap[base].fields[offset]
    if isinstance(obj_val, Pointer) and vm.heap_contains(obj_val.base):
        heap_obj = vm.heap_get(obj_val.base)
        # Try INDEX kind first (array-style), then PROPERTY (store_field default).
        offset_str = str(obj_val.offset)
        tv = heap_obj.fields.get(
            FieldName(offset_str, FieldKind.INDEX)
        ) or heap_obj.fields.get(FieldName(offset_str, FieldKind.PROPERTY))
        if tv is None:
            # For direct heap objects (obj_/arr_), the indirection is a no-op:
            # ADDRESS_OF returned identity, so the ref IS the object pointer.
            base_str = str(obj_val.base)
            if base_str.startswith(constants.OBJ_ADDR_PREFIX) or base_str.startswith(
                constants.ARR_ADDR_PREFIX
            ):
                tv = typed(obj_val, scalar(constants.TypeName.POINTER))
            else:
                sym = vm.fresh_symbolic(hint=f"*{obj_val}")
                tv = typed(sym, UNKNOWN)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: tv},
                reasoning=f"load *{obj_val} = {tv!r}",
            )
        )
    if isinstance(obj_val, Pointer) and not vm.heap_contains(obj_val.base):
        sym = vm.fresh_symbolic(hint=f"*{obj_val}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load *{obj_val} (not on heap) → {sym.name}",
            )
        )
    # Function pointer dereference is identity: (*fp)(args) == fp(args)
    if isinstance(obj_val, BoundFuncRef):
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed_from_runtime(obj_val)},
                reasoning=f"deref {obj_val} → {obj_val} (function pointer identity)",
            )
        )
    # Fallback: symbolic
    sym = vm.fresh_symbolic(hint=f"*{_symbolic_name(obj_val)}")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load_indirect on non-pointer {obj_val!r} → {sym.name}",
        )
    )


def _handle_load_field_indirect(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    """LOAD_FIELD_INDIRECT %obj %name: load field whose name is in a register."""
    from interpreter.handlers.calls import _try_user_function_call

    t = inst
    assert isinstance(t, LoadFieldIndirect)
    obj_val = _resolve_reg(vm, t.obj_reg).value
    field_name = _resolve_reg(vm, t.name_reg).value
    addr = _heap_addr(obj_val)
    if not addr or not vm.heap_contains(addr):
        sym = vm.fresh_symbolic(hint=f"{_symbolic_name(obj_val)}.{field_name}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load_field_indirect on non-heap {obj_val!r} → {sym.name}",
            )
        )
    heap_obj = vm.heap_get(addr)
    field_key = FieldName(str(field_name))
    if field_key in heap_obj.fields:
        tv = heap_obj.fields[field_key]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: tv},
                reasoning=f"load {addr}.{field_name} (indirect) = {tv!r}",
            )
        )
    # Field not found — check for __method_missing__ on the object
    mm_ref = _find_method_missing(heap_obj, ctx.registry, ctx.cfg)
    if mm_ref is not None:
        self_tv = typed(obj_val, heap_obj.type_hint)
        name_tv = typed(field_name, scalar("String"))
        return _try_user_function_call(
            mm_ref,
            [self_tv, name_tv],
            inst,
            vm,
            ctx.cfg,
            ctx.registry,
            ctx.current_label,
        )
    # No __method_missing__ — return symbolic
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {addr}.{field_name} (indirect, unknown) → {sym.name}",
        )
    )


def _handle_store_indirect(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    """STORE_INDIRECT %ptr %val: write through a Pointer (dereference)."""
    t = inst
    assert isinstance(t, StoreIndirect)
    obj_val = _resolve_reg(vm, t.ptr_reg).value
    tv = _resolve_reg(vm, t.value_reg)
    if isinstance(obj_val, Pointer):
        target_field = FieldName(str(obj_val.offset), FieldKind.INDEX)
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=obj_val.base,
                        field=target_field,
                        value=tv,
                    )
                ],
                reasoning=f"store *{obj_val} = {tv.value!r}",
            )
        )
    obj_desc = _symbolic_name(obj_val)
    logger.debug("store_indirect on non-pointer %s", obj_desc)
    return ExecutionResult.success(
        StateUpdate(
            reasoning=f"store_indirect on {obj_desc} = {val!r} (non-pointer, no-op)",
        )
    )


def _handle_store_field(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    t = inst
    assert isinstance(t, StoreField)
    obj_val = _resolve_reg(vm, t.obj_reg).value
    field_name = (
        t.field_name
        if isinstance(t.field_name, FieldName)
        else FieldName(str(t.field_name))
    )
    tv = _resolve_reg(vm, t.value_reg)
    addr = _heap_addr(obj_val)
    if addr and not vm.heap_contains(addr):
        # Materialise a synthetic heap entry for symbolic objects so that
        # field stores are persisted and subsequent loads return the value.
        vm.heap_set(addr, HeapObject(type_hint=_symbolic_type_hint(obj_val)))
    if not addr or not vm.heap_contains(addr):
        obj_desc = _symbolic_name(obj_val)
        logger.debug("store_field on unknown object %s.%s", obj_desc, field_name)
        return ExecutionResult.success(
            StateUpdate(
                reasoning=f"store {obj_desc}.{field_name} = {tv.value!r} (object not on heap, no-op)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            heap_writes=[
                HeapWrite(
                    obj_addr=addr,
                    field=field_name,
                    value=tv,
                )
            ],
            reasoning=f"store {addr}.{field_name} = {tv.value!r}",
        )
    )


def _handle_load_field(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    from interpreter.handlers.calls import _try_user_function_call

    t = inst
    assert isinstance(t, LoadField)
    obj_val = _resolve_reg(vm, t.obj_reg).value
    field_name = (
        t.field_name
        if isinstance(t.field_name, FieldName)
        else FieldName(str(t.field_name))
    )
    # Static field access on a ClassRef: look up via symbol table constants
    if isinstance(obj_val, ClassRef):
        symbol_table = ctx.symbol_table
        class_info = symbol_table.classes.get(ClassName(str(obj_val.name)))
        if class_info and str(field_name) in class_info.constants:
            raw = class_info.constants[str(field_name)]
            val = _parse_const(raw)
            static_tv = typed_from_runtime(val)
            logger.debug(
                "load_field ClassRef %s.%s = %r",
                obj_val.name,
                field_name,
                static_tv.value,
            )
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: static_tv},
                    reasoning=f"load class static {obj_val.name}.{field_name} = {static_tv.value!r}",
                )
            )
    addr = _heap_addr(obj_val)
    if addr and not vm.heap_contains(addr):
        # Materialise a synthetic heap entry for symbolic objects so that
        # repeated field accesses return the same symbolic value (deduplication).
        vm.heap_set(addr, HeapObject(type_hint=_symbolic_type_hint(obj_val)))
    if not addr or not vm.heap_contains(addr):
        obj_desc = _symbolic_name(obj_val)
        sym = vm.fresh_symbolic(hint=f"{obj_desc}.{field_name}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load {obj_desc}.{field_name} (not on heap) → {sym.name}",
            )
        )
    heap_obj = vm.heap_get(addr)
    if field_name in heap_obj.fields:
        tv = heap_obj.fields[field_name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: tv},
                reasoning=f"load {addr}.{field_name} = {tv!r}",
            )
        )
    # Field not found — check for __method_missing__ on the object
    mm_ref = _find_method_missing(heap_obj, ctx.registry, ctx.cfg)
    if mm_ref is not None:
        self_tv = typed(obj_val, heap_obj.type_hint)
        name_tv = typed(str(field_name), scalar("String"))
        return _try_user_function_call(
            mm_ref,
            [self_tv, name_tv],
            inst,
            vm,
            ctx.cfg,
            ctx.registry,
            ctx.current_label,
        )
    # No __method_missing__ — create symbolic and cache it
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    heap_obj.fields[field_name] = typed(sym, UNKNOWN)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
        )
    )


def _handle_store_index(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    t = inst
    assert isinstance(t, StoreIndex)
    arr_val = _resolve_reg(vm, t.arr_reg).value
    idx_val = _resolve_reg(vm, t.index_reg).value
    tv = _resolve_reg(vm, t.value_reg)
    addr = _heap_addr(arr_val)
    if addr and not vm.heap_contains(addr):
        # Materialise a synthetic heap entry for symbolic arrays so that
        # repeated index stores persist and are visible to later loads.
        vm.heap_set(addr, HeapObject(type_hint=_symbolic_type_hint(arr_val)))
    if not addr or not vm.heap_contains(addr):
        arr_desc = _symbolic_name(arr_val)
        logger.debug("store_index on unknown array %s[%s]", arr_desc, idx_val)
        return ExecutionResult.success(
            StateUpdate(
                reasoning=f"store {arr_desc}[{idx_val}] = {tv.value!r} (array not on heap, no-op)",
            )
        )
    idx_kind = _infer_index_kind(idx_val)
    return ExecutionResult.success(
        StateUpdate(
            heap_writes=[
                HeapWrite(
                    obj_addr=addr,
                    field=FieldName(str(idx_val), idx_kind),
                    value=tv,
                )
            ],
            reasoning=f"store {addr}[{idx_val}] = {tv.value!r}",
        )
    )


def _handle_load_index(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, LoadIndex)
    arr_val = _resolve_reg(vm, t.arr_reg).value
    idx_val = _resolve_reg(vm, t.index_reg).value
    addr = _heap_addr(arr_val)

    # Native string/list indexing — bypass heap for raw Python values.
    # Only applies when the value is NOT a heap reference.
    if isinstance(idx_val, int) and (not vm.heap_contains(addr)):
        if isinstance(arr_val, list):
            element = arr_val[idx_val]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: typed_from_runtime(element)},
                    reasoning=f"native index {arr_val!r}[{idx_val}] = {element!r}",
                )
            )
        if isinstance(arr_val, str) and not vm.heap_contains(addr):
            element = arr_val[idx_val]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: typed_from_runtime(element)},
                    reasoning=f"native index {arr_val!r}[{idx_val}] = {element!r}",
                )
            )
    if addr and not vm.heap_contains(addr):
        # Materialise a synthetic heap entry for symbolic arrays so that
        # repeated index accesses with the same key are deduplicated.
        vm.heap_set(addr, HeapObject(type_hint=_symbolic_type_hint(arr_val)))
    if not addr or not vm.heap_contains(addr):
        arr_desc = _symbolic_name(arr_val)
        sym = vm.fresh_symbolic(hint=f"{arr_desc}[{idx_val}]")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load {arr_desc}[{idx_val}] (not on heap) → {sym.name}",
            )
        )
    heap_obj = vm.heap_get(addr)
    idx_kind = _infer_index_kind(idx_val)
    key = FieldName(str(idx_val), idx_kind)
    if key in heap_obj.fields:
        tv = heap_obj.fields[key]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: tv},
                reasoning=f"load {addr}[{idx_val}] = {tv!r}",
            )
        )
    sym = vm.fresh_symbolic(hint=f"{addr}[{idx_val}]")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {addr}[{idx_val}] (unknown) → {sym.name}",
        )
    )
