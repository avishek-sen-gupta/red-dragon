"""Function & Class Registry, builtins, and local execution."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .ir import IRInstruction, Opcode
from .cfg import BasicBlock, CFG
from .vm import (
    VMState,
    SymbolicValue,
    HeapObject,
    StackFrame,
    StateUpdate,
    HeapWrite,
    NewObject,
    StackFramePush,
    ExecutionResult,
    Operators,
    _serialize_value,
    _resolve_reg,
    _is_symbolic,
    _heap_addr,
    _parse_const,
)
from . import constants

logger = logging.getLogger(__name__)


# ── Parse helpers ────────────────────────────────────────────────


@dataclass
class RefParseResult:
    """Result of parsing a function or class reference string."""

    matched: bool
    name: str = ""
    label: str = ""


class RefPatterns:
    """Compiled regex patterns for function/class references."""

    FUNC_RE = re.compile(constants.FUNC_REF_PATTERN)
    CLASS_RE = re.compile(constants.CLASS_REF_PATTERN)


def _parse_func_ref(val: Any) -> RefParseResult:
    """Parse '<function:name@label>' → RefParseResult."""
    if not isinstance(val, str):
        return RefParseResult(matched=False)
    m = RefPatterns.FUNC_RE.search(val)
    if not m:
        return RefParseResult(matched=False)
    return RefParseResult(matched=True, name=m.group(1), label=m.group(2))


def _parse_class_ref(val: Any) -> RefParseResult:
    """Parse '<class:name@label>' → RefParseResult."""
    if not isinstance(val, str):
        return RefParseResult(matched=False)
    m = RefPatterns.CLASS_RE.search(val)
    if not m:
        return RefParseResult(matched=False)
    return RefParseResult(matched=True, name=m.group(1), label=m.group(2))


# ── Registry ─────────────────────────────────────────────────────


@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[str, list[str]] = field(default_factory=dict)
    # class_name → {method_name → func_label}
    class_methods: dict[str, dict[str, str]] = field(default_factory=dict)
    # class_name → class_body_label
    classes: dict[str, str] = field(default_factory=dict)


def _scan_func_params(cfg: CFG) -> dict[str, list[str]]:
    """Extract parameter names from function blocks in the CFG."""
    result: dict[str, list[str]] = {}
    for label, block in cfg.blocks.items():
        if not label.startswith(constants.FUNC_LABEL_PREFIX):
            continue
        params = [
            str(inst.operands[0])[len(constants.PARAM_PREFIX) :]
            for inst in block.instructions
            if inst.opcode == Opcode.SYMBOLIC
            and inst.operands
            and str(inst.operands[0]).startswith(constants.PARAM_PREFIX)
        ]
        result[label] = params
    return result


def _scan_classes(
    instructions: list[IRInstruction],
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Scan IR to find classes and their methods.

    Returns (classes, class_methods) where:
    - classes: class_name → class_body_label
    - class_methods: class_name → {method_name → func_label}
    """
    classes: dict[str, str] = {}
    class_methods: dict[str, dict[str, str]] = {}

    # First pass: find class constants
    for inst in instructions:
        if inst.opcode != Opcode.CONST or not inst.operands:
            continue
        cr = _parse_class_ref(str(inst.operands[0]))
        if cr.matched:
            classes[cr.name] = cr.label

    # Second pass: identify class scopes and their methods
    in_class: str = ""
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.startswith(
                constants.CLASS_LABEL_PREFIX
            ) and not inst.label.startswith(constants.END_CLASS_LABEL_PREFIX):
                for cname, clabel in classes.items():
                    if inst.label == clabel:
                        in_class = cname
                        if cname not in class_methods:
                            class_methods[cname] = {}
                        break
            elif inst.label.startswith(constants.END_CLASS_LABEL_PREFIX):
                in_class = ""

        if in_class and inst.opcode == Opcode.CONST and inst.operands:
            fr = _parse_func_ref(str(inst.operands[0]))
            if fr.matched:
                class_methods[in_class][fr.name] = fr.label

    return classes, class_methods


def build_registry(instructions: list[IRInstruction], cfg: CFG) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()
    reg.func_params = _scan_func_params(cfg)
    reg.classes, reg.class_methods = _scan_classes(instructions)
    return reg


# ── Builtin function table ───────────────────────────────────────

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        return len(vm.heap[addr].fields)
    if isinstance(val, (list, tuple, str)):
        return len(val)
    return _UNCOMPUTABLE


def _builtin_range(args: list[Any], vm: VMState) -> Any:
    if any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    concrete = list(args)
    if len(concrete) == 1:
        return list(range(int(concrete[0])))
    if len(concrete) == 2:
        return list(range(int(concrete[0]), int(concrete[1])))
    if len(concrete) == 3:
        return list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
    return _UNCOMPUTABLE


def _builtin_print(args: list[Any], vm: VMState) -> Any:
    return None  # print returns None (the actual Python value)


def _builtin_int(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return int(args[0])
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_float(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return float(args[0])
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_str(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return str(args[0])
    return _UNCOMPUTABLE


def _builtin_bool(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return bool(args[0])
    return _UNCOMPUTABLE


def _builtin_abs(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return abs(args[0])
        except TypeError:
            pass
    return _UNCOMPUTABLE


def _builtin_max(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return max(args)
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_min(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return min(args)
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


class Builtins:
    """Table of built-in function implementations."""

    TABLE: dict[str, Any] = {
        "len": _builtin_len,
        "range": _builtin_range,
        "print": _builtin_print,
        "int": _builtin_int,
        "float": _builtin_float,
        "str": _builtin_str,
        "bool": _builtin_bool,
        "abs": _builtin_abs,
        "max": _builtin_max,
        "min": _builtin_min,
    }


# ── Local execution ──────────────────────────────────────────────


def _handle_const(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    raw = inst.operands[0] if inst.operands else "None"
    val = _parse_const(raw)
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
    for f in reversed(vm.call_stack):
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
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return ExecutionResult.not_handled()
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
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return ExecutionResult.not_handled()
    heap_obj = vm.heap[addr]
    if field_name in heap_obj.fields:
        val = heap_obj.fields[field_name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: _serialize_value(val)},
                reasoning=f"load {addr}.{field_name} = {val!r}",
            )
        )
    # Field not found — create symbolic
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
    if not addr or addr not in vm.heap:
        return ExecutionResult.not_handled()
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
    if not addr or addr not in vm.heap:
        return ExecutionResult.not_handled()
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
    return ExecutionResult.success(StateUpdate(reasoning=f"throw {val!r}"))


def _handle_branch_if(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    cond_val = _resolve_reg(vm, inst.operands[0])
    targets = inst.label.split(",")
    true_label = targets[0].strip()
    false_label = targets[1].strip() if len(targets) > 1 else None

    if _is_symbolic(cond_val):
        return ExecutionResult.not_handled()

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

    if _is_symbolic(lhs) or _is_symbolic(rhs):
        return ExecutionResult.not_handled()

    result = Operators.eval_binop(oper, lhs, rhs)
    if result is Operators.UNCOMPUTABLE:
        return ExecutionResult.not_handled()
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"binop {lhs!r} {oper} {rhs!r} = {result!r}",
        )
    )


def _handle_unop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    oper = inst.operands[0]
    operand = _resolve_reg(vm, inst.operands[1])
    if _is_symbolic(operand):
        return ExecutionResult.not_handled()
    result = Operators.eval_unop(oper, operand)
    if result is Operators.UNCOMPUTABLE:
        return ExecutionResult.not_handled()
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"unop {oper}{operand!r} = {result!r}",
        )
    )


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
        return ExecutionResult.not_handled()
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
    if params:
        new_vars[params[0]] = addr
    for i, arg in enumerate(args):
        if i + 1 < len(params):
            new_vars[params[i + 1]] = _serialize_value(arg)

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
    new_vars = {
        params[i]: _serialize_value(arg)
        for i, arg in enumerate(args)
        if i < len(params)
    }
    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(function_name=fname, return_label=current_label),
            next_label=flabel,
            reasoning=(
                f"call {fname}"
                f"({', '.join(repr(a) for a in args)}),"
                f" dispatch to {flabel}"
            ),
            var_writes=new_vars,
        )
    )


def _handle_call_function(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    **kwargs: Any,
) -> ExecutionResult:
    func_name = inst.operands[0]
    arg_regs = inst.operands[1:]
    args = [_resolve_reg(vm, a) for a in arg_regs]

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
        return ExecutionResult.not_handled()

    # 3. Class constructor
    ctor_result = _try_class_constructor_call(
        func_val, args, inst, vm, cfg, registry, current_label
    )
    if ctor_result.handled:
        return ctor_result

    # 4. User-defined function
    return _try_user_function_call(
        func_val, args, inst, vm, cfg, registry, current_label
    )


def _handle_call_method(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    **kwargs: Any,
) -> ExecutionResult:
    obj_val = _resolve_reg(vm, inst.operands[0])
    method_name = inst.operands[1]
    arg_regs = inst.operands[2:]
    args = [_resolve_reg(vm, a) for a in arg_regs]

    addr = _heap_addr(obj_val)
    type_hint = ""
    if addr and addr in vm.heap:
        type_hint = vm.heap[addr].type_hint or ""

    if not type_hint or type_hint not in registry.class_methods:
        return ExecutionResult.not_handled()

    methods = registry.class_methods[type_hint]
    func_label = methods.get(method_name, "")
    if not func_label or func_label not in cfg.blocks:
        return ExecutionResult.not_handled()

    params = registry.func_params.get(func_label, [])
    new_vars: dict[str, Any] = {}
    if params:
        new_vars[params[0]] = _serialize_value(obj_val)
    for i, arg in enumerate(args):
        if i + 1 < len(params):
            new_vars[params[i + 1]] = _serialize_value(arg)

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
        Opcode.BRANCH_IF: _handle_branch_if,
        Opcode.BINOP: _handle_binop,
        Opcode.UNOP: _handle_unop,
        Opcode.CALL_FUNCTION: _handle_call_function,
        Opcode.CALL_METHOD: _handle_call_method,
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
        )


def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
) -> ExecutionResult:
    """Try to execute an instruction without the LLM.

    Returns an ExecutionResult indicating whether the instruction was
    handled locally, and the StateUpdate if so.
    """
    return LocalExecutor.execute(inst, vm, cfg, registry, current_label, ip)
