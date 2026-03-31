"""Variable-related opcode handlers: CONST, LOAD_VAR, DECL_VAR, STORE_VAR, SYMBOLIC."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.address import Address
from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.instructions import (
    InstructionBase,
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Symbolic,
)
from interpreter.vm.vm import (
    VMState,
    ClosureEnvironment,
    ExecutionResult,
    StateUpdate,
    _resolve_reg,
    _parse_const,
)
from interpreter.vm.vm_types import HeapWrite
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import typed, typed_from_runtime
from interpreter import constants
from interpreter.handlers._common import _write_var_to_frame
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID

logger = logging.getLogger(__name__)


def _handle_const(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Const)
    func_symbol_table = ctx.func_symbol_table
    class_symbol_table = ctx.class_symbol_table
    raw = inst.operands[0] if inst.operands else "None"
    val = _parse_const(raw)

    # Symbol table lookup: produce BoundFuncRef for function labels
    func_ref_entry = None
    if isinstance(val, str) and val in func_symbol_table:
        func_ref_entry = func_symbol_table[val]

    if func_ref_entry is not None:
        closure_id = NO_CLOSURE_ID
        if len(vm.call_stack) > 1:
            enclosing = vm.current_frame
            env_id = enclosing.closure_env_id
            if env_id:
                # Reuse existing environment; sync any new local vars into it
                env = vm.closures[env_id]
                for k, v in enclosing.local_vars.items():
                    if k not in env.bindings:
                        env.bindings[k] = v
            else:
                env_id = ClosureId(f"{constants.ENV_ID_PREFIX}{vm.symbolic_counter}")
                vm.symbolic_counter += 1
                env = ClosureEnvironment(bindings=dict(enclosing.local_vars))
                vm.closures[env_id] = env
                enclosing.closure_env_id = env_id
                enclosing.captured_var_names = frozenset(enclosing.local_vars.keys())
            closure_id = ClosureId(f"closure_{vm.symbolic_counter}")
            vm.symbolic_counter += 1
            vm.closures[closure_id] = env
            logger.debug(
                "Captured closure %s (env %s) for %s: %s",
                closure_id,
                env_id,
                func_ref_entry.name,
                list(env.bindings.keys()),
            )
        val = BoundFuncRef(func_ref=func_ref_entry, closure_id=closure_id)
    # Class symbol table lookup: store ClassRef directly in register
    elif isinstance(val, str) and val in class_symbol_table:
        val = class_symbol_table[val]

    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed_from_runtime(val)},
            reasoning=f"const {raw!r} → {t.result_reg}",
        )
    )


def _handle_load_var(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, LoadVar)
    name = t.name
    # Alias-aware: if variable is backed by a heap object, read from heap
    for f in reversed(vm.call_stack):
        alias_ptr = f.var_heap_aliases.get(name)
        if alias_ptr and vm.heap_contains(alias_ptr.base):
            tv = vm.heap_get(alias_ptr.base).fields.get(
                FieldName(str(alias_ptr.offset), FieldKind.INDEX)
            )
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: tv},
                    reasoning=f"load {name} = {tv!r} (via heap alias {alias_ptr.base})",
                )
            )
        if name in f.local_vars:
            stored = f.local_vars[name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: stored},
                    reasoning=f"load {name} = {stored.value!r} → {t.result_reg}",
                )
            )
    # Variable not found — try field fallback strategy
    this_field = ctx.field_fallback.resolve_load(vm, name)
    if this_field is not None:
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: this_field},
                reasoning=f"load {name} = {this_field.value!r} (via implicit this.{name})",
            )
        )
    # Not found anywhere — create symbolic
    sym = vm.fresh_symbolic(hint=str(name))
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {name} (not found) → symbolic {sym.name}",
        )
    )


def _handle_decl_var(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    """DECL_VAR: always create/overwrite in the current frame (declaration)."""
    t = inst
    assert isinstance(t, DeclVar)
    name = t.name
    tv = _resolve_reg(vm, t.value_reg)
    return ExecutionResult.success(
        StateUpdate(
            var_writes={name: tv},
            reasoning=f"decl {name} = {tv.value!r}",
        )
    )


def _handle_store_var(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    """STORE_VAR: assignment — walk scope chain to find existing variable."""
    t = inst
    assert isinstance(t, StoreVar)
    name = t.name
    tv = _resolve_reg(vm, t.value_reg)
    # Walk scope chain: if variable exists in a parent frame, update it there.
    for frame in reversed(vm.call_stack):
        if name in frame.local_vars:
            _write_var_to_frame(vm, frame, name, tv, ctx)
            return ExecutionResult.success(
                StateUpdate(reasoning=f"store {name} = {tv.value!r} (scope chain)")
            )
    # Not found in any frame — try field fallback strategy
    fallback = ctx.field_fallback
    this_addr = fallback.resolve_store(vm, name)
    if this_addr is not None:
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=Address(this_addr),
                        field=FieldName(str(name)),
                        value=tv,
                    )
                ],
                reasoning=f"store {name} = {tv.value!r} (via implicit this.{name})",
            )
        )
    # Not found anywhere — create in current frame (new variable).
    return ExecutionResult.success(
        StateUpdate(
            var_writes={name: tv},
            reasoning=f"store {name} = {tv.value!r}",
        )
    )


def _handle_symbolic(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Symbolic)
    hint = t.hint
    frame = vm.current_frame
    # If this is a parameter and the value was pre-populated by a call,
    # use the concrete value instead of creating a symbolic.
    if isinstance(hint, str) and hint.startswith(constants.PARAM_PREFIX):
        param_name = VarName(hint[len(constants.PARAM_PREFIX) :])
        if param_name in frame.local_vars:
            stored = frame.local_vars[param_name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: stored},
                    reasoning=f"param {param_name} = {stored.value!r} (bound by caller)",
                )
            )
    sym = vm.fresh_symbolic(hint=hint)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"symbolic {sym.name} (hint={hint})",
        )
    )
