"""Local execution — opcode handlers and dispatch table."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.ir import IRInstruction, Opcode
from interpreter.cfg import CFG
from interpreter.vm import (
    VMState,
    SymbolicValue,
    HeapObject,
    ClosureEnvironment,
    ExceptionHandler,
    Pointer,
    StackFramePush,
    StateUpdate,
    HeapWrite,
    NewObject,
    RegionWrite,
    ExecutionResult,
    Operators,
    _serialize_value,
    _resolve_reg,
    _is_symbolic,
    _heap_addr,
    _parse_const,
)
from interpreter.registry import FunctionRegistry, _parse_func_ref, _parse_class_ref
from interpreter.builtins import Builtins, _builtin_array_of
from interpreter.unresolved_call import UnresolvedCallResolver, SymbolicResolver
from interpreter import constants

_DEFAULT_RESOLVER = SymbolicResolver()

logger = logging.getLogger(__name__)


# ── Symbolic helpers ─────────────────────────────────────────────


def _symbolic_name(val: Any) -> str:
    """Get a human-readable name for a value, suitable for symbolic hints."""
    if isinstance(val, SymbolicValue):
        return val.name
    if isinstance(val, dict) and val.get("__symbolic__"):
        return val.get("name", "?")
    return repr(val)


def _symbolic_type_hint(val: Any) -> str:
    """Extract a type hint from a symbolic value (SymbolicValue or dict)."""
    if isinstance(val, SymbolicValue):
        return val.type_hint or ""
    if isinstance(val, dict) and val.get("__symbolic__"):
        return val.get("type_hint", "")
    return ""


# ── Opcode handlers ─────────────────────────────────────────────


def _handle_const(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    raw = inst.operands[0] if inst.operands else "None"
    val = _parse_const(raw)

    # Closure capture: when a function ref is created inside another function,
    # link it to a shared ClosureEnvironment so mutations persist across calls.
    # If the enclosing frame already has an environment (second closure from
    # the same factory), reuse it; otherwise create a new one.
    if len(vm.call_stack) > 1 and isinstance(val, str):
        fr = _parse_func_ref(val)
        if fr.matched:
            enclosing = vm.current_frame
            env_id = enclosing.closure_env_id
            if env_id:
                # Reuse existing environment; sync any new local vars into it
                env = vm.closures[env_id]
                for k, v in enclosing.local_vars.items():
                    if k not in env.bindings:
                        env.bindings[k] = v
            else:
                env_id = f"{constants.ENV_ID_PREFIX}{vm.symbolic_counter}"
                vm.symbolic_counter += 1
                env = ClosureEnvironment(bindings=dict(enclosing.local_vars))
                vm.closures[env_id] = env
                enclosing.closure_env_id = env_id
                enclosing.captured_var_names = frozenset(enclosing.local_vars.keys())
            closure_id = f"closure_{vm.symbolic_counter}"
            vm.symbolic_counter += 1
            vm.closures[closure_id] = env
            val = f"<function:{fr.name}@{fr.label}#{closure_id}>"
            logger.debug(
                "Captured closure %s (env %s) for %s: %s",
                closure_id,
                env_id,
                fr.name,
                list(env.bindings.keys()),
            )

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: val},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )
    )


def _handle_load_var(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    name = inst.operands[0]
    # Alias-aware: if variable is backed by a heap object, read from heap
    for f in reversed(vm.call_stack):
        alias_ptr = f.var_heap_aliases.get(name)
        if alias_ptr and alias_ptr.base in vm.heap:
            val = vm.heap[alias_ptr.base].fields.get(str(alias_ptr.offset))
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {name} = {val!r} (via heap alias {alias_ptr.base})",
                )
            )
        if name in f.local_vars:
            val = f.local_vars[name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {name} = {val!r} → {inst.result_reg}",
                )
            )
    # Variable not found — create symbolic
    sym = vm.fresh_symbolic(hint=name)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"load {name} (not found) → symbolic {sym.name}",
        )
    )


def _handle_store_var(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    name = inst.operands[0]
    val = _resolve_reg(vm, inst.operands[1])
    return ExecutionResult.success(
        StateUpdate(
            var_writes={name: _serialize_value(val)},
            reasoning=f"store {name} = {val!r}",
        )
    )


def _handle_address_of(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """ADDRESS_OF var_name: promote variable to heap and return a Pointer."""
    name = inst.operands[0]
    frame = vm.current_frame

    # Already aliased — return the existing Pointer
    if name in frame.var_heap_aliases:
        ptr = frame.var_heap_aliases[name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: ptr},
                reasoning=f"address_of {name} → {ptr} (already aliased)",
            )
        )

    # Look up the variable's current value across the call stack
    current_val = None
    for f in reversed(vm.call_stack):
        if name in f.local_vars:
            current_val = f.local_vars[name]
            break

    # Function reference: &func_name returns the reference unchanged
    # (identity semantics — our model already uses references for functions)
    if isinstance(current_val, str) and _parse_func_ref(current_val).matched:
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: current_val},
                reasoning=f"address_of {name} → {current_val} (function ref, identity)",
            )
        )

    # If variable holds a heap address (struct/array/symbolic), wrap it in a Pointer
    # but do NOT alias the variable — structs are already on the heap, so
    # LOAD_VAR should continue to return the heap address string directly.
    addr = _heap_addr(current_val)
    if addr and addr in vm.heap:
        ptr = Pointer(base=addr, offset=0)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: ptr},
                reasoning=f"address_of {name} → {ptr} (existing heap object)",
            )
        )

    # Promote primitive to heap: allocate a HeapObject with field "0"
    mem_addr = f"mem_{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    vm.heap[mem_addr] = HeapObject(type_hint=None, fields={"0": current_val})
    ptr = Pointer(base=mem_addr, offset=0)
    frame.var_heap_aliases[name] = ptr
    logger.debug("address_of: promoted %s=%r to heap %s", name, current_val, mem_addr)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: ptr},
            reasoning=f"address_of {name} → {ptr} (promoted to heap {mem_addr})",
        )
    )


def _handle_branch(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    return ExecutionResult.success(
        StateUpdate(
            next_label=inst.label,
            reasoning=f"branch → {inst.label}",
        )
    )


def _handle_symbolic(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    hint = inst.operands[0] if inst.operands else ""
    frame = vm.current_frame
    # If this is a parameter and the value was pre-populated by a call,
    # use the concrete value instead of creating a symbolic.
    if isinstance(hint, str) and hint.startswith(constants.PARAM_PREFIX):
        param_name = hint[len(constants.PARAM_PREFIX) :]
        if param_name in frame.local_vars:
            val = frame.local_vars[param_name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"param {param_name} = {val!r} (bound by caller)",
                )
            )
    sym = vm.fresh_symbolic(hint=hint)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"symbolic {sym.name} (hint={hint})",
        )
    )


def _handle_new_object(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    type_hint = inst.operands[0] if inst.operands else ""
    # Dereference: if type_hint is a variable holding a class ref,
    # extract the canonical class name (e.g. Foo → __anon_class_0).
    for frame in reversed(vm.call_stack):
        if type_hint in frame.local_vars:
            cr = _parse_class_ref(str(frame.local_vars[type_hint]))
            if cr.matched:
                type_hint = cr.name
            break
    addr = f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint or None)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint} → {addr}",
        )
    )


def _handle_new_array(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    type_hint = inst.operands[0] if inst.operands else ""
    addr = f"{constants.ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return ExecutionResult.success(
        StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint or None)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint}[] → {addr}",
        )
    )


def _handle_store_field(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    obj_val = _resolve_reg(vm, inst.operands[0])
    field_name = inst.operands[1]
    val = _resolve_reg(vm, inst.operands[2])
    # Pointer field/dereference write
    if isinstance(obj_val, Pointer):
        # *ptr = val — dereference writes to the offset field
        target_field = str(obj_val.offset) if field_name == "*" else field_name
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=obj_val.base,
                        field=target_field,
                        value=_serialize_value(val),
                    )
                ],
                reasoning=f"store {obj_val.base}.{target_field} = {val!r} (via Pointer)",
            )
        )
    addr = _heap_addr(obj_val)
    if addr and addr not in vm.heap:
        # Materialise a synthetic heap entry for symbolic objects so that
        # field stores are persisted and subsequent loads return the value.
        vm.heap[addr] = HeapObject(type_hint=_symbolic_type_hint(obj_val))
    if not addr or addr not in vm.heap:
        obj_desc = _symbolic_name(obj_val)
        logger.debug("store_field on unknown object %s.%s", obj_desc, field_name)
        return ExecutionResult.success(
            StateUpdate(
                reasoning=f"store {obj_desc}.{field_name} = {val!r} (object not on heap, no-op)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            heap_writes=[
                HeapWrite(
                    obj_addr=addr,
                    field=field_name,
                    value=_serialize_value(val),
                )
            ],
            reasoning=f"store {addr}.{field_name} = {val!r}",
        )
    )


def _handle_load_field(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    obj_val = _resolve_reg(vm, inst.operands[0])
    field_name = inst.operands[1]
    # Pointer field/dereference access
    if isinstance(obj_val, Pointer) and obj_val.base in vm.heap:
        heap_obj = vm.heap[obj_val.base]
        # *ptr — dereference reads from the offset field
        if field_name == "*":
            val = heap_obj.fields.get(str(obj_val.offset))
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load *{obj_val} = {val!r}",
                )
            )
        # ptr->field — struct pointer field access (reads field from the object)
        if field_name in heap_obj.fields:
            val = heap_obj.fields[field_name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {obj_val.base}.{field_name} = {val!r} (via Pointer)",
                )
            )
    if isinstance(obj_val, Pointer) and obj_val.base not in vm.heap:
        sym = vm.fresh_symbolic(hint=f"*{obj_val}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load *{obj_val} (not on heap) → {sym.name}",
            )
        )
    # In C, *fp where fp is a function pointer is equivalent to fp.
    if (
        field_name == "*"
        and isinstance(obj_val, str)
        and _parse_func_ref(obj_val).matched
    ):
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: obj_val},
                reasoning=f"deref {obj_val} → {obj_val} (dereference of function pointer is identity)",
            )
        )
    addr = _heap_addr(obj_val)
    if addr and addr not in vm.heap:
        # Materialise a synthetic heap entry for symbolic objects so that
        # repeated field accesses return the same symbolic value (deduplication).
        vm.heap[addr] = HeapObject(type_hint=_symbolic_type_hint(obj_val))
    if not addr or addr not in vm.heap:
        obj_desc = _symbolic_name(obj_val)
        sym = vm.fresh_symbolic(hint=f"{obj_desc}.{field_name}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {obj_desc}.{field_name} (not on heap) → {sym.name}",
            )
        )
    heap_obj = vm.heap[addr]
    if field_name in heap_obj.fields:
        val = heap_obj.fields[field_name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: _serialize_value(val)},
                reasoning=f"load {addr}.{field_name} = {val!r}",
            )
        )
    # Field not found — create symbolic and cache it
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    heap_obj.fields[field_name] = sym
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
        )
    )


def _handle_store_index(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    arr_val = _resolve_reg(vm, inst.operands[0])
    idx_val = _resolve_reg(vm, inst.operands[1])
    val = _resolve_reg(vm, inst.operands[2])
    addr = _heap_addr(arr_val)
    if addr and addr not in vm.heap:
        # Materialise a synthetic heap entry for symbolic arrays so that
        # repeated index stores persist and are visible to later loads.
        vm.heap[addr] = HeapObject(type_hint=_symbolic_type_hint(arr_val))
    if not addr or addr not in vm.heap:
        arr_desc = _symbolic_name(arr_val)
        logger.debug("store_index on unknown array %s[%s]", arr_desc, idx_val)
        return ExecutionResult.success(
            StateUpdate(
                reasoning=f"store {arr_desc}[{idx_val}] = {val!r} (array not on heap, no-op)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            heap_writes=[
                HeapWrite(
                    obj_addr=addr,
                    field=str(idx_val),
                    value=_serialize_value(val),
                )
            ],
            reasoning=f"store {addr}[{idx_val}] = {val!r}",
        )
    )


def _handle_load_index(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    arr_val = _resolve_reg(vm, inst.operands[0])
    idx_val = _resolve_reg(vm, inst.operands[1])
    addr = _heap_addr(arr_val)

    # Native string/list indexing — bypass heap for raw Python values.
    # Only applies when the value is NOT a heap reference.
    if isinstance(idx_val, int) and (addr not in vm.heap):
        if isinstance(arr_val, list):
            element = arr_val[idx_val]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(element)},
                    reasoning=f"native index {arr_val!r}[{idx_val}] = {element!r}",
                )
            )
        if isinstance(arr_val, str) and addr not in vm.heap:
            element = arr_val[idx_val]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(element)},
                    reasoning=f"native index {arr_val!r}[{idx_val}] = {element!r}",
                )
            )
    if addr and addr not in vm.heap:
        # Materialise a synthetic heap entry for symbolic arrays so that
        # repeated index accesses with the same key are deduplicated.
        vm.heap[addr] = HeapObject(type_hint=_symbolic_type_hint(arr_val))
    if not addr or addr not in vm.heap:
        arr_desc = _symbolic_name(arr_val)
        sym = vm.fresh_symbolic(hint=f"{arr_desc}[{idx_val}]")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {arr_desc}[{idx_val}] (not on heap) → {sym.name}",
            )
        )
    heap_obj = vm.heap[addr]
    key = str(idx_val)
    if key in heap_obj.fields:
        val = heap_obj.fields[key]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: _serialize_value(val)},
                reasoning=f"load {addr}[{idx_val}] = {val!r}",
            )
        )
    sym = vm.fresh_symbolic(hint=f"{addr}[{idx_val}]")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"load {addr}[{idx_val}] (unknown) → {sym.name}",
        )
    )


def _handle_return(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
    return ExecutionResult.success(
        StateUpdate(
            return_value=_serialize_value(val),
            call_pop=True,
            reasoning=f"return {val!r}",
        )
    )


def _handle_throw(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
    if vm.exception_stack:
        handler = vm.exception_stack.pop()
        # Redirect to the first catch label (or finally if no catch)
        target = (
            handler.catch_labels[0]
            if handler.catch_labels
            else handler.finally_label or handler.end_label
        )
        return ExecutionResult.success(
            StateUpdate(
                next_label=target, reasoning=f"throw {val!r} → caught by {target}"
            )
        )
    return ExecutionResult.success(StateUpdate(reasoning=f"throw {val!r} (uncaught)"))


def _handle_try_push(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    catch_labels_str, finally_label, end_label = (
        inst.operands[0],
        inst.operands[1],
        inst.operands[2],
    )
    catch_labels = [lbl.strip() for lbl in catch_labels_str.split(",") if lbl.strip()]
    vm.exception_stack.append(
        ExceptionHandler(
            catch_labels=catch_labels,
            finally_label=finally_label,
            end_label=end_label,
        )
    )
    return ExecutionResult.success(
        StateUpdate(reasoning=f"push exception handler → catch={catch_labels}")
    )


def _handle_try_pop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    vm.exception_stack.pop()
    return ExecutionResult.success(StateUpdate(reasoning="pop exception handler"))


def _handle_branch_if(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    cond_val = _resolve_reg(vm, inst.operands[0])
    targets = inst.label.split(",")
    true_label = targets[0].strip()
    false_label = targets[1].strip() if len(targets) > 1 else None

    if _is_symbolic(cond_val):
        # Symbolic condition — deterministically take the true branch
        # and record the assumption as a path condition
        sym_desc = _symbolic_name(cond_val)
        return ExecutionResult.success(
            StateUpdate(
                next_label=true_label,
                path_condition=f"assuming {sym_desc} is True",
                reasoning=f"branch_if {sym_desc} (symbolic) → {true_label} (assumed true)",
            )
        )

    taken = bool(cond_val)
    chosen = true_label if taken else false_label
    return ExecutionResult.success(
        StateUpdate(
            next_label=chosen,
            path_condition=f"{inst.operands[0]} is {taken}",
            reasoning=f"branch_if {cond_val!r} → {chosen}",
        )
    )


def _handle_binop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    oper = inst.operands[0]
    lhs = _resolve_reg(vm, inst.operands[1])
    rhs = _resolve_reg(vm, inst.operands[2])

    # Pointer arithmetic: Pointer +/- int or int + Pointer
    # Also handles heap address strings (array decay to pointer in C)
    lhs_ptr = (
        lhs
        if isinstance(lhs, Pointer)
        else (
            Pointer(base=lhs, offset=0)
            if isinstance(lhs, str) and _heap_addr(lhs) and _heap_addr(lhs) in vm.heap
            else None
        )
    )
    rhs_ptr = (
        rhs
        if isinstance(rhs, Pointer)
        else (
            Pointer(base=rhs, offset=0)
            if isinstance(rhs, str) and _heap_addr(rhs) and _heap_addr(rhs) in vm.heap
            else None
        )
    )
    if lhs_ptr and rhs_ptr:
        # Pointer - Pointer: offset difference (must share same base)
        if oper == "-" and lhs_ptr.base == rhs_ptr.base:
            diff = lhs_ptr.offset - rhs_ptr.offset
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: diff},
                    reasoning=f"pointer diff {lhs!r} - {rhs!r} = {diff}",
                )
            )
        # Pointer relational comparison (same base)
        if oper in ("<", ">", "<=", ">=", "==", "!=") and lhs_ptr.base == rhs_ptr.base:
            result = Operators.eval_binop(oper, lhs_ptr.offset, rhs_ptr.offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"pointer cmp {lhs!r} {oper} {rhs!r} = {result!r}",
                )
            )
    if oper in ("+", "-") and (lhs_ptr or rhs_ptr):
        ptr = lhs_ptr or rhs_ptr
        offset_val = rhs if lhs_ptr else lhs
        if isinstance(offset_val, (int, float)):
            new_offset = (
                ptr.offset + int(offset_val)
                if oper == "+" or not lhs_ptr
                else ptr.offset - int(offset_val)
            )
            result_ptr = Pointer(base=ptr.base, offset=new_offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: result_ptr},
                    reasoning=f"pointer arith {lhs!r} {oper} {rhs!r} = {result_ptr!r}",
                )
            )

    if _is_symbolic(lhs) or _is_symbolic(rhs):
        lhs_desc = _symbolic_name(lhs)
        rhs_desc = _symbolic_name(rhs)
        sym = vm.fresh_symbolic(hint=f"{lhs_desc} {oper} {rhs_desc}")
        sym.constraints = [f"{lhs_desc} {oper} {rhs_desc}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"binop {lhs_desc} {oper} {rhs_desc} → symbolic {sym.name}",
            )
        )

    result = Operators.eval_binop(oper, lhs, rhs)
    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{lhs!r} {oper} {rhs!r}")
        sym.constraints = [f"{lhs!r} {oper} {rhs!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"binop {lhs!r} {oper} {rhs!r} → uncomputable, symbolic {sym.name}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"binop {lhs!r} {oper} {rhs!r} = {result!r}",
        )
    )


def _handle_unop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    oper = inst.operands[0]
    operand = _resolve_reg(vm, inst.operands[1])
    # Address-of (&) on a value that is already a reference (function ref or
    # heap object) returns the reference unchanged — our model already uses
    # references rather than inline values for these.
    if oper == "&":
        addr = _heap_addr(operand)
        if addr and (_parse_func_ref(operand).matched or addr in vm.heap):
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: operand},
                    reasoning=f"unop &{operand} → {operand} (address-of reference is identity)",
                )
            )
    if _is_symbolic(operand):
        op_desc = _symbolic_name(operand)
        sym = vm.fresh_symbolic(hint=f"{oper}{op_desc}")
        sym.constraints = [f"{oper}{op_desc}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"unop {oper}{op_desc} → symbolic {sym.name}",
            )
        )
    result = Operators.eval_unop(oper, operand)
    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{oper}{operand!r}")
        sym.constraints = [f"{oper}{operand!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"unop {oper}{operand!r} → uncomputable, symbolic {sym.name}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"unop {oper}{operand!r} = {result!r}",
        )
    )


# ── Continuation handlers ────────────────────────────────────────


def _handle_set_continuation(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """SET_CONTINUATION: operands = [name, label]. Write name → label into continuation table."""
    name = inst.operands[0]
    label = inst.operands[1]
    return ExecutionResult.success(
        StateUpdate(
            continuation_writes={name: label},
            reasoning=f"set_continuation {name} → {label}",
        )
    )


def _handle_resume_continuation(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """RESUME_CONTINUATION: operands = [name]. Branch to label if set, else fall through."""
    name = inst.operands[0]
    target = vm.continuations.get(name)
    if target:
        return ExecutionResult.success(
            StateUpdate(
                next_label=target,
                continuation_clear=name,
                reasoning=f"resume_continuation {name} → {target}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            continuation_clear=name,
            reasoning=f"resume_continuation {name} (not set, fall through)",
        )
    )


# ── Region handlers ──────────────────────────────────────────────


def _handle_alloc_region(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """ALLOC_REGION: operands[0] = size literal. Allocate a zeroed byte region."""
    size = _resolve_reg(vm, inst.operands[0])
    if _is_symbolic(size):
        sym = vm.fresh_symbolic(hint="region_addr")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"alloc_region(symbolic size) → {sym.name}",
            )
        )
    addr = f"{constants.REGION_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return ExecutionResult.success(
        StateUpdate(
            new_regions={addr: int(size)},
            register_writes={inst.result_reg: addr},
            reasoning=f"alloc_region({size}) → {addr}",
        )
    )


def _handle_write_region(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """WRITE_REGION: operands = [region_reg, offset_reg, length_literal, value_reg].

    Write bytes from value_reg (a list[int]) into the region at the given offset.
    """
    region_addr = _resolve_reg(vm, inst.operands[0])
    offset = _resolve_reg(vm, inst.operands[1])
    length = inst.operands[2]
    value = _resolve_reg(vm, inst.operands[3])

    has_symbolic_elements = isinstance(value, list) and any(
        _is_symbolic(v) for v in value
    )
    if (
        _is_symbolic(region_addr)
        or _is_symbolic(offset)
        or _is_symbolic(value)
        or has_symbolic_elements
    ):
        return ExecutionResult.success(
            StateUpdate(
                reasoning=f"write_region(symbolic args) — no-op",
            )
        )

    data = list(value)[: int(length)] if isinstance(value, (list, bytes)) else []
    return ExecutionResult.success(
        StateUpdate(
            region_writes=[
                RegionWrite(
                    region_addr=str(region_addr),
                    offset=int(offset),
                    data=data,
                )
            ],
            reasoning=f"write_region({region_addr}, offset={offset}, len={length})",
        )
    )


def _handle_load_region(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """LOAD_REGION: operands = [region_reg, offset_reg, length_literal].

    Read bytes from the region and return as list[int].
    """
    region_addr = _resolve_reg(vm, inst.operands[0])
    offset = _resolve_reg(vm, inst.operands[1])
    length = inst.operands[2]

    if _is_symbolic(region_addr) or _is_symbolic(offset):
        sym = vm.fresh_symbolic(hint=f"region_load")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load_region(symbolic) → {sym.name}",
            )
        )

    addr_str = str(region_addr)
    if addr_str not in vm.regions:
        sym = vm.fresh_symbolic(hint=f"region_load({addr_str})")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load_region({addr_str}) — unknown region → {sym.name}",
            )
        )

    start = int(offset)
    end = start + int(length)
    data = list(vm.regions[addr_str][start:end])
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: data},
            reasoning=f"load_region({addr_str}, offset={start}, len={length}) = {data}",
        )
    )


# ── Call helpers ─────────────────────────────────────────────────


def _try_builtin_call(
    func_name: str,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
) -> ExecutionResult:
    """Attempt to handle a call via the builtin table."""
    if func_name not in Builtins.TABLE:
        return ExecutionResult.not_handled()
    result = Builtins.TABLE[func_name](args, vm)
    if result is Operators.UNCOMPUTABLE:
        # Builtin couldn't compute (symbolic args) — create symbolic result
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
        sym.constraints = [f"{func_name}({args_desc})"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"builtin {func_name}({args_desc}) → symbolic {sym.name} (uncomputable)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: _serialize_value(result)},
            reasoning=(
                f"builtin {func_name}"
                f"({', '.join(repr(a) for a in args)}) = {result!r}"
            ),
        )
    )


def _try_class_constructor_call(
    func_val: Any,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
) -> ExecutionResult:
    """Attempt to handle a call as a class constructor."""
    cr = _parse_class_ref(func_val)
    if not cr.matched:
        return ExecutionResult.not_handled()

    class_name, class_label = cr.name, cr.label
    methods = registry.class_methods.get(class_name, {})
    init_label = methods.get("__init__")

    # Allocate heap object
    addr = f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    vm.heap[addr] = HeapObject(type_hint=class_name)

    if not init_label or init_label not in cfg.blocks:
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: addr},
                new_objects=[NewObject(addr=addr, type_hint=class_name)],
                reasoning=f"new {class_name}() → {addr} (no __init__)",
            )
        )

    params = registry.func_params.get(init_label, [])
    new_vars: dict[str, Any] = {}
    # Python emits self as explicit first param; Java/C++/C# do not
    has_explicit_self = bool(params) and params[0] == constants.PARAM_SELF
    if has_explicit_self:
        # Python-style: first param is self/this, rest are constructor args
        new_vars[params[0]] = addr
        for i, arg in enumerate(args):
            if i + 1 < len(params):
                new_vars[params[i + 1]] = _serialize_value(arg)
    else:
        # Java/C++/C#-style: this is implicit, all params are constructor args
        new_vars[constants.PARAM_THIS] = addr
        for i, arg in enumerate(args):
            if i < len(params):
                new_vars[params[i]] = _serialize_value(arg)

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: addr},
            call_push=StackFramePush(
                function_name=f"{class_name}.__init__",
                return_label=current_label,
            ),
            next_label=init_label,
            reasoning=(
                f"new {class_name}"
                f"({', '.join(repr(a) for a in args)}) → {addr},"
                " dispatch __init__"
            ),
            var_writes=new_vars,
        )
    )


def _try_user_function_call(
    func_val: Any,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
) -> ExecutionResult:
    """Attempt to dispatch a call to a user-defined function."""
    fr = _parse_func_ref(func_val)
    if not fr.matched:
        return ExecutionResult.not_handled()

    fname, flabel = fr.name, fr.label
    if flabel not in cfg.blocks:
        return ExecutionResult.not_handled()

    params = registry.func_params.get(flabel, [])
    param_vars = {
        params[i]: _serialize_value(arg)
        for i, arg in enumerate(args)
        if i < len(params)
    }
    # Inject 'arguments' array so rest params can slice it
    param_vars["arguments"] = _builtin_array_of([_serialize_value(a) for a in args], vm)

    # Inject captured closure variables; parameter bindings take priority
    closure_env: ClosureEnvironment | None = None
    captured: dict[str, Any] = {}
    if fr.closure_id:
        closure_env = vm.closures.get(fr.closure_id)
        if closure_env:
            captured = closure_env.bindings

    new_vars = {k: _serialize_value(v) for k, v in captured.items()} if captured else {}
    new_vars.update(param_vars)
    if captured:
        logger.debug("Injecting closure vars for %s: %s", fname, list(captured.keys()))

    closure_env_id = fr.closure_id if closure_env else ""
    captured_var_names = list(captured.keys()) if closure_env else []

    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(
                function_name=fname,
                return_label=current_label,
                closure_env_id=closure_env_id,
                captured_var_names=captured_var_names,
            ),
            next_label=flabel,
            reasoning=(
                f"call {fname}"
                f"({', '.join(repr(a) for a in args)}),"
                f" dispatch to {flabel}"
            ),
            var_writes=new_vars,
        )
    )


# ── Compound call handlers ──────────────────────────────────────


def _handle_call_function(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    **kwargs: Any,
) -> ExecutionResult:
    func_name = inst.operands[0]
    arg_regs = inst.operands[1:]
    args = [_resolve_reg(vm, a) for a in arg_regs]

    # 0. Try I/O provider (for __cobol_* calls)
    if (
        vm.io_provider
        and isinstance(func_name, str)
        and func_name.startswith("__cobol_")
    ):
        result = vm.io_provider.handle_call(func_name, args)
        if result is not Operators.UNCOMPUTABLE:
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(result)},
                    reasoning=f"io_provider {func_name}({args!r}) = {result!r}",
                )
            )
        # UNCOMPUTABLE — fall through to symbolic wrapping
        sym = vm.fresh_symbolic(hint=f"{func_name}(…)")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"io_provider {func_name} → symbolic (uncomputable)",
            )
        )

    # 1. Try builtins
    builtin_result = _try_builtin_call(func_name, args, inst, vm)
    if builtin_result.handled:
        return builtin_result

    # 2. Look up the function/class via scope chain
    func_val = ""
    for f in reversed(vm.call_stack):
        if func_name in f.local_vars:
            func_val = f.local_vars[func_name]
            break
    if not func_val:
        # Unknown function — resolve via configured strategy
        return call_resolver.resolve_call(func_name, args, inst, vm)

    # 2b. Scala-style apply: arr(i) on heap-backed arrays → index into fields.
    if len(args) == 1 and isinstance(args[0], int):
        addr = _heap_addr(func_val)
        if addr and addr in vm.heap:
            heap_obj = vm.heap[addr]
            idx_key = str(args[0])
            if idx_key in heap_obj.fields:
                element = heap_obj.fields[idx_key]
                return ExecutionResult.success(
                    StateUpdate(
                        register_writes={inst.result_reg: _serialize_value(element)},
                        reasoning=f"heap call-index {func_name}({args[0]}) = {element!r}",
                    )
                )

    # 2c. Native string/list indexing — e.g. Scala s1(i) → s1[i]
    # Exclude VM internal references (functions, classes, heap addresses).
    if (
        (
            isinstance(func_val, list)
            or (isinstance(func_val, str) and not func_val.startswith("<"))
        )
        and len(args) == 1
        and isinstance(args[0], int)
    ):
        element = func_val[args[0]]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: _serialize_value(element)},
                reasoning=f"native call-index {func_name}({args[0]}) = {element!r}",
            )
        )

    # 3. Class constructor
    ctor_result = _try_class_constructor_call(
        func_val, args, inst, vm, cfg, registry, current_label
    )
    if ctor_result.handled:
        return ctor_result

    # 4. User-defined function
    user_result = _try_user_function_call(
        func_val, args, inst, vm, cfg, registry, current_label
    )
    if user_result.handled:
        return user_result

    # 5. Not a recognized function ref — resolve via configured strategy
    return call_resolver.resolve_call(func_name, args, inst, vm)


def _handle_call_method(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    **kwargs: Any,
) -> ExecutionResult:
    obj_val = _resolve_reg(vm, inst.operands[0])
    method_name = inst.operands[1]
    arg_regs = inst.operands[2:]
    args = [_resolve_reg(vm, a) for a in arg_regs]

    # If the object is a FUNC_REF, invoke it directly (e.g. .call(), .apply())
    func_ref = _parse_func_ref(obj_val)
    if func_ref.matched:
        return _try_user_function_call(
            obj_val, args, inst, vm, cfg, registry, current_label
        )

    # Method builtins: subList, substring, slice, etc.
    method_fn = Builtins.METHOD_TABLE.get(method_name)
    if method_fn is not None:
        result = method_fn(obj_val, args, vm)
        if result is not Operators.UNCOMPUTABLE:
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(result)},
                    reasoning=f"method builtin {method_name}({obj_val!r}, {args}) = {result!r}",
                )
            )

    addr = _heap_addr(obj_val)
    type_hint = ""
    if addr and addr in vm.heap:
        type_hint = vm.heap[addr].type_hint or ""

    if not type_hint or type_hint not in registry.class_methods:
        # Unknown object type — resolve via configured strategy
        obj_desc = _symbolic_name(obj_val)
        return call_resolver.resolve_method(obj_desc, method_name, args, inst, vm)

    methods = registry.class_methods[type_hint]
    func_label = methods.get(method_name, "")
    # Walk parent chain for inherited methods
    if not func_label or func_label not in cfg.blocks:
        for parent in registry.class_parents.get(type_hint, []):
            parent_methods = registry.class_methods.get(parent, {})
            candidate = parent_methods.get(method_name, "")
            if candidate and candidate in cfg.blocks:
                func_label = candidate
                break
    if not func_label or func_label not in cfg.blocks:
        # Known type but unknown method — resolve via configured strategy
        return call_resolver.resolve_method(type_hint, method_name, args, inst, vm)

    params = registry.func_params.get(func_label, [])
    new_vars: dict[str, Any] = {}
    if params:
        new_vars[params[0]] = _serialize_value(obj_val)
    for i, arg in enumerate(args):
        if i + 1 < len(params):
            new_vars[params[i + 1]] = _serialize_value(arg)
    # Inject 'arguments' array (explicit args only, not 'this')
    new_vars["arguments"] = _builtin_array_of([_serialize_value(a) for a in args], vm)

    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(
                function_name=f"{type_hint}.{method_name}",
                return_label=current_label,
            ),
            next_label=func_label,
            reasoning=(
                f"call {type_hint}.{method_name}"
                f"({', '.join(repr(a) for a in args)}),"
                f" dispatch to {func_label}"
            ),
            var_writes=new_vars,
        )
    )


def _handle_call_unknown(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    **kwargs: Any,
) -> ExecutionResult:
    """Handle CALL_UNKNOWN — dynamic call target, resolve via configured strategy."""
    target_val = _resolve_reg(vm, inst.operands[0])
    arg_regs = inst.operands[1:]
    args = [_resolve_reg(vm, a) for a in arg_regs]

    # If the target resolves to a FUNC_REF, invoke it directly
    user_result = _try_user_function_call(
        target_val, args, inst, vm, cfg, registry, current_label
    )
    if user_result.handled:
        return user_result

    target_desc = _symbolic_name(target_val)
    return call_resolver.resolve_call(target_desc, args, inst, vm)


# ── Dispatch table and entry point ──────────────────────────────


class LocalExecutor:
    """Dispatches IR instructions to handler functions for local execution."""

    DISPATCH: dict[Opcode, Any] = {
        Opcode.CONST: _handle_const,
        Opcode.LOAD_VAR: _handle_load_var,
        Opcode.STORE_VAR: _handle_store_var,
        Opcode.BRANCH: _handle_branch,
        Opcode.SYMBOLIC: _handle_symbolic,
        Opcode.NEW_OBJECT: _handle_new_object,
        Opcode.NEW_ARRAY: _handle_new_array,
        Opcode.STORE_FIELD: _handle_store_field,
        Opcode.LOAD_FIELD: _handle_load_field,
        Opcode.STORE_INDEX: _handle_store_index,
        Opcode.LOAD_INDEX: _handle_load_index,
        Opcode.RETURN: _handle_return,
        Opcode.THROW: _handle_throw,
        Opcode.TRY_PUSH: _handle_try_push,
        Opcode.TRY_POP: _handle_try_pop,
        Opcode.BRANCH_IF: _handle_branch_if,
        Opcode.BINOP: _handle_binop,
        Opcode.UNOP: _handle_unop,
        Opcode.CALL_FUNCTION: _handle_call_function,
        Opcode.CALL_METHOD: _handle_call_method,
        Opcode.CALL_UNKNOWN: _handle_call_unknown,
        Opcode.SET_CONTINUATION: _handle_set_continuation,
        Opcode.RESUME_CONTINUATION: _handle_resume_continuation,
        Opcode.ALLOC_REGION: _handle_alloc_region,
        Opcode.WRITE_REGION: _handle_write_region,
        Opcode.LOAD_REGION: _handle_load_region,
        Opcode.ADDRESS_OF: _handle_address_of,
    }

    @classmethod
    def execute(
        cls,
        inst: IRInstruction,
        vm: VMState,
        cfg: CFG,
        registry: FunctionRegistry,
        current_label: str = "",
        ip: int = 0,
        call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    ) -> ExecutionResult:
        handler = cls.DISPATCH.get(inst.opcode)
        if not handler:
            return ExecutionResult.not_handled()
        return handler(
            inst=inst,
            vm=vm,
            cfg=cfg,
            registry=registry,
            current_label=current_label,
            ip=ip,
            call_resolver=call_resolver,
        )


def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
) -> ExecutionResult:
    """Try to execute an instruction without the LLM.

    Returns an ExecutionResult indicating whether the instruction was
    handled locally, and the StateUpdate if so.
    """
    return LocalExecutor.execute(
        inst,
        vm,
        cfg,
        registry,
        current_label,
        ip,
        call_resolver,
    )
