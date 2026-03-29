"""Call opcode handlers: CALL_FUNCTION, CALL_METHOD, CALL_UNKNOWN + helpers."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.address import Address
from interpreter.field_name import FieldName, FieldKind
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.instructions import (
    InstructionBase,
    CallFunction,
    CallCtorFunction,
    CallMethod,
    CallUnknown,
)
from interpreter.ir import CodeLabel
from interpreter.vm.vm import (
    VMState,
    HeapObject,
    ClosureEnvironment,
    Pointer,
    StackFramePush,
    StateUpdate,
    NewObject,
    ExecutionResult,
    Operators,
    _resolve_reg,
    _heap_addr,
    _is_symbolic,
    _parse_const,
)
from interpreter.vm.vm_types import BuiltinResult
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.vm.builtins import Builtins, _builtin_array_of
from interpreter.overload.overload_resolver import (
    NullOverloadResolver,
    OverloadResolver,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, TypeExpr, parse_type, pointer, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter import constants
from interpreter.handlers._common import _resolve_call_args, _symbolic_name
from interpreter.handlers.memory import (
    _find_method_missing,
    _resolve_method_delegation_target,
)

logger = logging.getLogger(__name__)


def _unwrap_builtin_result(result: BuiltinResult, name: str) -> TypedValue:
    """Extract TypedValue from BuiltinResult, warning if heap address returned bare."""
    if isinstance(result.value, TypedValue):
        return result.value
    if isinstance(result.value, (Pointer, str)) and _heap_addr(result.value):
        logger.warning(
            "Builtin %s returned bare heap address %r, expected TypedValue",
            name,
            result.value,
        )
    return typed_from_runtime(result.value)


def _try_builtin_call(
    func_name: str,
    args: list[TypedValue],
    inst: InstructionBase,
    vm: VMState,
) -> ExecutionResult:
    """Attempt to handle a call via the builtin table."""
    builtin_fn = Builtins.lookup_builtin(
        func_name if isinstance(func_name, FuncName) else FuncName(func_name)
    )
    if builtin_fn is None:
        return ExecutionResult.not_handled()
    result = builtin_fn(args, vm)
    if result.value is Operators.UNCOMPUTABLE:
        args_desc = ", ".join(_symbolic_name(a.value) for a in args)
        sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
        sym.constraints = [f"{func_name}({args_desc})"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"builtin {func_name}({args_desc}) → symbolic {sym.name} (uncomputable)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={
                inst.result_reg: _unwrap_builtin_result(result, func_name)
            },
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
            reasoning=(
                f"builtin {func_name}"
                f"({', '.join(repr(a.value) for a in args)}) = {result.value!r}"
            ),
        )
    )


def _try_class_constructor_call(
    func_val: Any,
    args: list[TypedValue],
    inst: InstructionBase,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: CodeLabel,
    overload_resolver: OverloadResolver = NullOverloadResolver(),
    type_env: TypeEnvironment = None,
    type_hint: TypeExpr = UNKNOWN,
) -> ExecutionResult:
    """Attempt to handle a call as a class constructor."""
    from types import MappingProxyType
    from interpreter.types.type_environment import TypeEnvironment as _TE

    if type_env is None:
        type_env = _TE(
            register_types=MappingProxyType({}),
            var_types=MappingProxyType({}),
        )

    if not isinstance(func_val, ClassRef):
        return ExecutionResult.not_handled()
    class_name, class_label = func_val.name, func_val.label

    init_labels = registry.lookup_methods(class_name, FuncName("__init__"))
    if init_labels:
        init_sigs = type_env.method_signatures.get(scalar(str(class_name)), {}).get(
            "__init__", []
        )
        if len(init_sigs) != len(init_labels):
            logger.warning("sig/label count mismatch for %s.__init__", class_name)
            init_label = init_labels[0]
        else:
            winner = overload_resolver.resolve(init_sigs, args)
            init_label = init_labels[winner]
    else:
        init_label = ""

    # Allocate heap object
    addr = f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    resolved_type = type_hint if type_hint else scalar(str(class_name))
    vm.heap_set(Address(addr), HeapObject(type_hint=resolved_type))
    ptr_tv = typed(Pointer(base=Address(addr), offset=0), pointer(resolved_type))

    if not init_label or init_label not in cfg.blocks:
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: ptr_tv},
                new_objects=[NewObject(addr=Address(addr), type_hint=resolved_type)],
                reasoning=f"new {class_name}() → {addr} (no __init__)",
            )
        )

    params = registry.func_params.get(init_label, [])
    new_vars: dict[VarName, Any] = {}
    # Python emits self, Java/C#/Kotlin/Scala/C++ emit this as explicit first param
    has_explicit_self = bool(params) and params[0] in constants.SELF_PARAM_NAMES
    if has_explicit_self:
        # Explicit self/this: first param is self/this, rest are constructor args
        new_vars[VarName(params[0])] = ptr_tv
        for i, arg in enumerate(args):
            if i + 1 < len(params):
                new_vars[VarName(params[i + 1])] = arg
    else:
        # Java/C++/C#-style: this is implicit, all params are constructor args
        new_vars[VarName(constants.PARAM_THIS)] = ptr_tv
        for i, arg in enumerate(args):
            if i < len(params):
                new_vars[VarName(params[i])] = arg

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: ptr_tv},
            call_push=StackFramePush(
                function_name=FuncName(f"{class_name}.__init__"),
                return_label=current_label,
                is_ctor=True,
            ),
            next_label=init_label,
            reasoning=(
                f"new {class_name}"
                f"({', '.join(repr(a.value) for a in args)}) → {addr},"
                " dispatch __init__"
            ),
            var_writes=new_vars,
        )
    )


def _try_user_function_call(
    func_val: Any,
    args: list[TypedValue],
    inst: InstructionBase,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: CodeLabel,
) -> ExecutionResult:
    """Attempt to dispatch a call to a user-defined function."""
    if not isinstance(func_val, BoundFuncRef):
        return ExecutionResult.not_handled()

    fname, flabel = func_val.func_ref.name, func_val.func_ref.label
    if flabel not in cfg.blocks:
        return ExecutionResult.not_handled()

    params = registry.func_params.get(flabel, [])
    param_vars = {
        VarName(params[i]): arg for i, arg in enumerate(args) if i < len(params)
    }
    # Inject 'arguments' array so rest params can slice it
    args_result = _builtin_array_of(list(args), vm)
    param_vars[VarName("arguments")] = args_result.value

    # Inject captured closure variables; parameter bindings take priority
    closure_env: ClosureEnvironment | None = None
    captured: dict[VarName, Any] = {}
    if func_val.closure_id:
        closure_env = vm.closures.get(func_val.closure_id)
        if closure_env:
            captured = {k: v for k, v in closure_env.bindings.items()}

    new_vars = dict(captured) if captured else {}
    new_vars.update(param_vars)
    if captured:
        logger.debug("Injecting closure vars for %s: %s", fname, list(captured.keys()))

    closure_env_id = func_val.closure_id if closure_env else ""
    captured_var_names = (
        [VarName(k) if isinstance(k, str) else k for k in captured.keys()]
        if closure_env
        else []
    )

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
                f"({', '.join(repr(a.value) for a in args)}),"
                f" dispatch to {flabel}"
            ),
            var_writes=new_vars,
            new_objects=args_result.new_objects,
            heap_writes=args_result.heap_writes,
        )
    )


def _handle_call_function(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    t = inst
    assert isinstance(t, CallFunction)
    base_name = t.func_name
    arg_regs = list(t.args)
    args = _resolve_call_args(vm, arg_regs)

    # 0. Try I/O provider (for __cobol_* calls)
    if (
        vm.io_provider
        and isinstance(base_name, FuncName)
        and base_name.startswith("__cobol_")
    ):
        result = vm.io_provider.handle_call(base_name, args)
        if result is not Operators.UNCOMPUTABLE:
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: typed_from_runtime(result)},
                    reasoning=f"io_provider {base_name}({[a.value for a in args]!r}) = {result!r}",
                )
            )
        # UNCOMPUTABLE — fall through to symbolic wrapping
        sym = vm.fresh_symbolic(hint=f"{base_name}(…)")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"io_provider {base_name} → symbolic (uncomputable)",
            )
        )

    # 1. Try builtins
    builtin_result = _try_builtin_call(base_name, args, inst, vm)
    if builtin_result.handled:
        return builtin_result

    # 2. Look up the function/class via scope chain
    func_val = ""
    lookup_key = (
        VarName(str(base_name)) if isinstance(base_name, (str, FuncName)) else base_name
    )
    for f in reversed(vm.call_stack):
        if lookup_key in f.local_vars:
            func_val = f.local_vars[lookup_key].value
            break
    if not func_val:
        # Unknown function — resolve via configured strategy
        return ctx.call_resolver.resolve_call(
            base_name, [a.value for a in args], inst, vm
        )

    # 2b. Scala-style apply: arr(i) on heap-backed arrays → index into fields.
    if len(args) == 1 and isinstance(args[0].value, int):
        addr = _heap_addr(func_val)
        if addr and vm.heap_contains(addr):
            heap_obj = vm.heap_get(addr)
            idx_key = FieldName(str(args[0].value), FieldKind.INDEX)
            if idx_key in heap_obj.fields:
                tv = heap_obj.fields[idx_key]
                return ExecutionResult.success(
                    StateUpdate(
                        register_writes={t.result_reg: tv},
                        reasoning=f"heap call-index {base_name}({args[0].value}) = {tv!r}",
                    )
                )
            # Out-of-bounds on heap array → symbolic (do NOT fall through to 2c).
            sym = vm.fresh_symbolic(hint=f"{base_name}({args[0].value})")
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: typed(sym, UNKNOWN)},
                    reasoning=f"heap call-index {base_name}({args[0].value}) out of bounds → symbolic",
                )
            )

    # 2c. Native string/list indexing — e.g. Scala s1(i) → s1[i]
    # Exclude VM internal references (functions, classes, heap addresses).
    # ClassRef / BoundFuncRef objects are excluded by the isinstance check.
    if (
        isinstance(func_val, (list, str))
        and not (isinstance(func_val, str) and func_val.startswith("<"))
        and not (
            isinstance(func_val, str)
            and func_val.startswith(constants.FUNC_LABEL_PREFIX)
        )
        and not vm.heap_contains(_heap_addr(func_val))
        and len(args) == 1
        and isinstance(args[0].value, int)
    ):
        element = func_val[args[0].value]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed_from_runtime(element)},
                reasoning=f"native call-index {base_name}({args[0].value}) = {element!r}",
            )
        )

    # 3. Class constructor
    ctor_result = _try_class_constructor_call(
        func_val,
        args,
        inst,
        vm,
        ctx.cfg,
        ctx.registry,
        ctx.current_label,
        overload_resolver=ctx.overload_resolver,
        type_env=ctx.type_env,
        type_hint=parse_type(str(base_name)) if base_name else UNKNOWN,
    )
    if ctor_result.handled:
        return ctor_result

    # 4. User-defined function
    user_result = _try_user_function_call(
        func_val, args, inst, vm, ctx.cfg, ctx.registry, ctx.current_label
    )
    if user_result.handled:
        return user_result

    # 5. Not a recognized function ref — resolve via configured strategy
    return ctx.call_resolver.resolve_call(base_name, [a.value for a in args], inst, vm)


def _handle_call_ctor(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    """Handle CALL_CTOR: typed constructor call with TypeExpr type_hint."""
    t = inst
    assert isinstance(t, CallCtorFunction)
    func_name = t.func_name
    arg_regs = list(t.args)
    args = _resolve_call_args(vm, arg_regs)

    # Look up the ClassRef via scope chain
    func_val = ""
    ctor_key = (
        VarName(str(func_name)) if isinstance(func_name, (str, FuncName)) else func_name
    )
    for f in reversed(vm.call_stack):
        if ctor_key in f.local_vars:
            func_val = f.local_vars[ctor_key].value
            break
    if not func_val:
        return ctx.call_resolver.resolve_call(
            func_name, [a.value for a in args], inst, vm
        )

    # Dispatch to constructor with the typed type_hint
    ctor_result = _try_class_constructor_call(
        func_val,
        args,
        inst,
        vm,
        ctx.cfg,
        ctx.registry,
        ctx.current_label,
        overload_resolver=ctx.overload_resolver,
        type_env=ctx.type_env,
        type_hint=t.type_hint,
    )
    if ctor_result.handled:
        return ctor_result

    # Fallback: try as user function (e.g., factory functions named like classes)
    user_result = _try_user_function_call(
        func_val, args, inst, vm, ctx.cfg, ctx.registry, ctx.current_label
    )
    if user_result.handled:
        return user_result

    return ctx.call_resolver.resolve_call(func_name, [a.value for a in args], inst, vm)


def _handle_call_method(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    t = inst
    assert isinstance(t, CallMethod)
    obj_val = _resolve_reg(vm, t.obj_reg)
    method_name = t.method_name
    arg_regs = list(t.args)
    args = _resolve_call_args(vm, arg_regs)

    # If the object is a FUNC_REF, invoke it directly (e.g. .call(), .apply())
    if isinstance(obj_val.value, BoundFuncRef):
        return _try_user_function_call(
            obj_val.value, args, inst, vm, ctx.cfg, ctx.registry, ctx.current_label
        )

    # Static method dispatch: Class.method() where object is a ClassRef
    if isinstance(obj_val.value, ClassRef):
        class_name = obj_val.value.name
        func_labels = ctx.registry.lookup_methods(class_name, method_name)
        if func_labels:
            func_label = func_labels[0]
            bound_ref = BoundFuncRef(
                func_ref=FuncRef(name=FuncName(str(method_name)), label=func_label),
                closure_id="",
            )
            return _try_user_function_call(
                bound_ref, args, inst, vm, ctx.cfg, ctx.registry, ctx.current_label
            )

    # Method builtins: subList, substring, slice, etc.
    method_fn = Builtins.lookup_method_builtin(method_name)
    if method_fn is not None:
        result = method_fn(obj_val, args, vm)
        if result.value is not Operators.UNCOMPUTABLE:
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={
                        t.result_reg: _unwrap_builtin_result(result, method_name)
                    },
                    new_objects=result.new_objects,
                    heap_writes=result.heap_writes,
                    reasoning=f"method builtin {method_name}({obj_val.value!r}, {[a.value for a in args]}) = {result.value!r}",
                )
            )

    addr = _heap_addr(obj_val.value)
    type_hint = ""
    if addr and vm.heap_contains(addr):
        type_hint = vm.heap_get(addr).type_hint or ""
    class_key = ClassName(str(type_hint)) if type_hint else ClassName("")

    if not type_hint or class_key not in ctx.registry.class_methods:
        # Check if method exists as a callable field on the heap object
        # (e.g., Lua table OOP: t.method = function(...) end)
        # Inject obj as first arg (self) — mirrors colon-call convention.
        if addr and vm.heap_contains(addr):
            field_tv = vm.heap_get(addr).fields.get(FieldName(str(method_name)))
            if field_tv and isinstance(field_tv.value, BoundFuncRef):
                return _try_user_function_call(
                    field_tv.value,
                    [obj_val] + args,
                    inst,
                    vm,
                    ctx.cfg,
                    ctx.registry,
                    ctx.current_label,
                )
        # Unknown object type — resolve via configured strategy
        obj_desc = _symbolic_name(obj_val.value)
        return ctx.call_resolver.resolve_method(
            obj_desc, method_name, [a.value for a in args], inst, vm
        )

    func_labels = ctx.registry.lookup_methods(class_key, method_name)
    if func_labels:
        sigs = ctx.type_env.method_signatures.get(scalar(str(type_hint)), {}).get(
            str(method_name), []
        )
        if len(sigs) != len(func_labels):
            logger.warning("sig/label count mismatch for %s.%s", type_hint, method_name)
            func_label = func_labels[0]
        else:
            winner = ctx.overload_resolver.resolve(sigs, args)
            func_label = func_labels[winner]
    else:
        func_label = ""
    # Walk parent chain for inherited methods
    if not func_label or func_label not in ctx.cfg.blocks:
        for parent in ctx.registry.class_parents.get(class_key, []):
            parent_labels = ctx.registry.lookup_methods(parent, method_name)
            if not parent_labels:
                continue
            parent_sigs = ctx.type_env.method_signatures.get(
                scalar(str(parent)), {}
            ).get(str(method_name), [])
            if len(parent_sigs) != len(parent_labels):
                logger.warning(
                    "sig/label count mismatch for %s.%s", parent, method_name
                )
                candidate = parent_labels[0]
            else:
                winner = ctx.overload_resolver.resolve(parent_sigs, args)
                candidate = parent_labels[winner]
            if candidate and candidate in ctx.cfg.blocks:
                func_label = candidate
                break
    if not func_label or func_label not in ctx.cfg.blocks:
        # Known type but unknown method — follow __method_missing__ delegation chain
        if addr:
            delegation = _resolve_method_delegation_target(
                addr, method_name, vm, ctx.registry, ctx.cfg
            )
            if delegation is not None:
                inner_addr, inner_tv = delegation
                inner_type = str(vm.heap_get(inner_addr).type_hint or "")
                inner_labels = ctx.registry.lookup_methods(
                    ClassName(inner_type), method_name
                )
                inner_sigs = ctx.type_env.method_signatures.get(
                    scalar(inner_type), {}
                ).get(str(method_name), [])
                if len(inner_sigs) != len(inner_labels):
                    logger.warning(
                        "sig/label count mismatch for %s.%s",
                        inner_type,
                        method_name,
                    )
                    target_label = inner_labels[0]
                else:
                    winner = ctx.overload_resolver.resolve(inner_sigs, args)
                    target_label = inner_labels[winner]
                if target_label in ctx.cfg.blocks:
                    func_label = target_label
                    # Re-bind obj_val to the inner object for correct 'self'
                    obj_val = inner_tv
                    addr = inner_addr
        if not func_label or func_label not in ctx.cfg.blocks:
            # No delegation target found — resolve via configured strategy
            return ctx.call_resolver.resolve_method(
                type_hint, method_name, [a.value for a in args], inst, vm
            )

    params = ctx.registry.func_params.get(func_label, [])
    new_vars: dict[VarName, Any] = {}
    if params:
        new_vars[VarName(params[0])] = obj_val
    for i, arg in enumerate(args):
        if i + 1 < len(params):
            new_vars[VarName(params[i + 1])] = arg
    # Inject 'arguments' array (explicit args only, not 'this')
    args_result = _builtin_array_of(list(args), vm)
    new_vars[VarName("arguments")] = typed(args_result.value, UNKNOWN)

    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(
                function_name=FuncName(f"{type_hint}.{method_name}"),
                return_label=ctx.current_label,
            ),
            next_label=func_label,
            reasoning=(
                f"call {type_hint}.{method_name}"
                f"({', '.join(repr(a.value) for a in args)}),"
                f" dispatch to {func_label}"
            ),
            var_writes=new_vars,
            new_objects=args_result.new_objects,
            heap_writes=args_result.heap_writes,
        )
    )


def _handle_call_unknown(
    inst: InstructionBase,
    vm: VMState,
    ctx: Any,
) -> ExecutionResult:
    """Handle CALL_UNKNOWN — dynamic call target, resolve via configured strategy."""
    t = inst
    assert isinstance(t, CallUnknown)
    target_val = _resolve_reg(vm, t.target_reg)
    arg_regs = list(t.args)
    args = [_resolve_reg(vm, a) for a in arg_regs]

    # If the target resolves to a FUNC_REF, invoke it directly
    user_result = _try_user_function_call(
        target_val.value, args, inst, vm, ctx.cfg, ctx.registry, ctx.current_label
    )
    if user_result.handled:
        return user_result

    target_desc = _symbolic_name(target_val.value)
    return ctx.call_resolver.resolve_call(
        target_desc, [a.value for a in args], inst, vm
    )
