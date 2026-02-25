"""Function & Class Registry, builtins, and local execution."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ir import IRInstruction, Opcode
from .cfg import BasicBlock, CFG
from .vm import (
    VMState, SymbolicValue, HeapObject, StackFrame,
    StateUpdate, HeapWrite, NewObject, StackFramePush,
    _serialize_value, _resolve_reg, _is_symbolic, _heap_addr,
    _parse_const, _eval_binop, _eval_unop,
)


# ── Parse helpers ────────────────────────────────────────────────

_FUNC_RE = re.compile(r"<function:(\w+)@(\w+)>")
_CLASS_RE = re.compile(r"<class:(\w+)@(\w+)>")


def _parse_func_ref(val: Any) -> tuple[str, str] | None:
    """Parse '<function:name@label>' → (name, label) or None."""
    if not isinstance(val, str):
        return None
    m = _FUNC_RE.search(val)
    return (m.group(1), m.group(2)) if m else None


def _parse_class_ref(val: Any) -> tuple[str, str] | None:
    """Parse '<class:name@label>' → (name, label) or None."""
    if not isinstance(val, str):
        return None
    m = _CLASS_RE.search(val)
    return (m.group(1), m.group(2)) if m else None


# ── Registry ─────────────────────────────────────────────────────

@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[str, list[str]] = field(default_factory=dict)
    # class_name → {method_name → func_label}
    class_methods: dict[str, dict[str, str]] = field(default_factory=dict)
    # class_name → class_body_label
    classes: dict[str, str] = field(default_factory=dict)


def build_registry(instructions: list[IRInstruction], cfg: CFG) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()

    # 1. Extract parameter names from func blocks
    for label, block in cfg.blocks.items():
        if not label.startswith("func_"):
            continue
        params = []
        for inst in block.instructions:
            if inst.opcode == Opcode.SYMBOLIC and inst.operands:
                hint = str(inst.operands[0])
                if hint.startswith("param:"):
                    params.append(hint[6:])
        reg.func_params[label] = params

    # 2. Find classes and their methods by scanning the IR linearly
    #    Methods are <function:NAME@LABEL> constants between class_X and
    #    end_class_X labels.
    current_class: str | None = None
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            cm = _CLASS_RE.search(inst.label)
            if inst.label.startswith("class_") and not inst.label.startswith("end_class_"):
                # Entering a class body — extract class name from the
                # next CONST <class:Name@...> or from the label itself.
                # We'll set current_class when we see the class const.
                pass
            elif inst.label.startswith("end_class_"):
                current_class = None

        if inst.opcode == Opcode.CONST and inst.operands:
            val = str(inst.operands[0])
            cr = _parse_class_ref(val)
            if cr:
                class_name, class_label = cr
                reg.classes[class_name] = class_label
                # Now scan backwards: set current_class for the scope we
                # just exited. Instead, we'll use a second pass below.

    # Second pass: identify class scopes and their methods
    in_class: str | None = None
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.startswith("class_") and not inst.label.startswith("end_class_"):
                # Try to find which class this label belongs to
                for cname, clabel in reg.classes.items():
                    if inst.label == clabel:
                        in_class = cname
                        if cname not in reg.class_methods:
                            reg.class_methods[cname] = {}
                        break
            elif inst.label.startswith("end_class_"):
                in_class = None

        if in_class and inst.opcode == Opcode.CONST and inst.operands:
            fr = _parse_func_ref(str(inst.operands[0]))
            if fr:
                method_name, func_label = fr
                reg.class_methods[in_class][method_name] = func_label

    return reg


# ── Builtin function table ───────────────────────────────────────

def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return None
    val = args[0]
    # Heap array/object — count fields
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        return len(vm.heap[addr].fields)
    if isinstance(val, (list, tuple, str)):
        return len(val)
    return None


def _builtin_range(args: list[Any], vm: VMState) -> Any:
    concrete = []
    for a in args:
        if _is_symbolic(a):
            return None
        concrete.append(a)
    if len(concrete) == 1:
        return list(range(int(concrete[0])))
    if len(concrete) == 2:
        return list(range(int(concrete[0]), int(concrete[1])))
    if len(concrete) == 3:
        return list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
    return None


def _builtin_print(args: list[Any], vm: VMState) -> Any:
    return None  # print returns None


def _builtin_int(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return int(args[0])
        except (ValueError, TypeError):
            pass
    return None


def _builtin_float(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return float(args[0])
        except (ValueError, TypeError):
            pass
    return None


def _builtin_str(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return str(args[0])
    return None


def _builtin_bool(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return bool(args[0])
    return None


def _builtin_abs(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return abs(args[0])
        except TypeError:
            pass
    return None


def _builtin_max(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return max(args)
        except (ValueError, TypeError):
            pass
    return None


def _builtin_min(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return min(args)
        except (ValueError, TypeError):
            pass
    return None


_BUILTINS: dict[str, Any] = {
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

def _try_execute_locally(inst: IRInstruction, vm: VMState,
                         cfg: CFG | None = None,
                         registry: FunctionRegistry | None = None,
                         current_label: str = "",
                         ip: int = 0) -> StateUpdate | None:
    """Try to execute an instruction without the LLM.

    Returns a StateUpdate if the instruction can be handled mechanically,
    or None if LLM interpretation is needed.
    """
    op = inst.opcode
    frame = vm.current_frame

    if op == Opcode.CONST:
        # %r = const <literal>
        raw = inst.operands[0] if inst.operands else "None"
        val = _parse_const(raw)
        return StateUpdate(
            register_writes={inst.result_reg: val},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )

    if op == Opcode.LOAD_VAR:
        # %r = load_var <name>
        name = inst.operands[0]
        # Walk the call stack (current frame first, then outer scopes)
        for f in reversed(vm.call_stack):
            if name in f.local_vars:
                val = f.local_vars[name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {name} = {val!r} → {inst.result_reg}",
                )
        # Variable not found — create symbolic
        sym = vm.fresh_symbolic(hint=name)
        return StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"load {name} (not found) → symbolic {sym.name}",
        )

    if op == Opcode.STORE_VAR:
        # store_var <name>, %val
        name = inst.operands[0]
        val = _resolve_reg(vm, inst.operands[1])
        return StateUpdate(
            var_writes={name: _serialize_value(val)},
            reasoning=f"store {name} = {val!r}",
        )

    if op == Opcode.BRANCH:
        # branch <label>
        return StateUpdate(
            next_label=inst.label,
            reasoning=f"branch → {inst.label}",
        )

    if op == Opcode.SYMBOLIC:
        # symbolic %r, <hint>
        hint = inst.operands[0] if inst.operands else None
        # If this is a parameter and the value was pre-populated by a call,
        # use the concrete value instead of creating a symbolic.
        if isinstance(hint, str) and hint.startswith("param:"):
            param_name = hint[6:]
            if param_name in frame.local_vars:
                val = frame.local_vars[param_name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"param {param_name} = {val!r} (bound by caller)",
                )
        sym = vm.fresh_symbolic(hint=hint)
        return StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"symbolic {sym.name} (hint={hint})",
        )

    if op == Opcode.NEW_OBJECT:
        # %r = new_object <type>
        type_hint = inst.operands[0] if inst.operands else None
        addr = f"obj_{vm.symbolic_counter}"
        vm.symbolic_counter += 1
        return StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint} → {addr}",
        )

    if op == Opcode.NEW_ARRAY:
        # %r = new_array <type>, %size
        type_hint = inst.operands[0] if inst.operands else None
        addr = f"arr_{vm.symbolic_counter}"
        vm.symbolic_counter += 1
        return StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint}[] → {addr}",
        )

    if op == Opcode.STORE_FIELD:
        # store_field %obj, <field>, %val
        obj_val = _resolve_reg(vm, inst.operands[0])
        field_name = inst.operands[1]
        val = _resolve_reg(vm, inst.operands[2])
        addr = _heap_addr(obj_val)
        if addr and addr in vm.heap:
            return StateUpdate(
                heap_writes=[HeapWrite(obj_addr=addr, field=field_name,
                                       value=_serialize_value(val))],
                reasoning=f"store {addr}.{field_name} = {val!r}",
            )
        # Object not on heap — need LLM
        return None

    if op == Opcode.LOAD_FIELD:
        # %r = load_field %obj, <field>
        obj_val = _resolve_reg(vm, inst.operands[0])
        field_name = inst.operands[1]
        addr = _heap_addr(obj_val)
        if addr and addr in vm.heap:
            heap_obj = vm.heap[addr]
            if field_name in heap_obj.fields:
                val = heap_obj.fields[field_name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {addr}.{field_name} = {val!r}",
                )
            # Field not found — create symbolic
            sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
            heap_obj.fields[field_name] = sym
            return StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
            )
        return None

    if op == Opcode.STORE_INDEX:
        # store_index %arr, %idx, %val
        arr_val = _resolve_reg(vm, inst.operands[0])
        idx_val = _resolve_reg(vm, inst.operands[1])
        val = _resolve_reg(vm, inst.operands[2])
        addr = _heap_addr(arr_val)
        if addr and addr in vm.heap:
            return StateUpdate(
                heap_writes=[HeapWrite(obj_addr=addr, field=str(idx_val),
                                       value=_serialize_value(val))],
                reasoning=f"store {addr}[{idx_val}] = {val!r}",
            )
        return None

    if op == Opcode.LOAD_INDEX:
        # %r = load_index %arr, %idx
        arr_val = _resolve_reg(vm, inst.operands[0])
        idx_val = _resolve_reg(vm, inst.operands[1])
        addr = _heap_addr(arr_val)
        if addr and addr in vm.heap:
            heap_obj = vm.heap[addr]
            key = str(idx_val)
            if key in heap_obj.fields:
                val = heap_obj.fields[key]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {addr}[{idx_val}] = {val!r}",
                )
            sym = vm.fresh_symbolic(hint=f"{addr}[{idx_val}]")
            return StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {addr}[{idx_val}] (unknown) → {sym.name}",
            )
        return None

    if op == Opcode.RETURN:
        # return %val
        val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
        return StateUpdate(
            return_value=_serialize_value(val),
            call_pop=True,
            reasoning=f"return {val!r}",
        )

    if op == Opcode.THROW:
        val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
        return StateUpdate(
            reasoning=f"throw {val!r}",
        )

    if op == Opcode.BRANCH_IF:
        # branch_if %cond, <label_true>,<label_false>
        cond_val = _resolve_reg(vm, inst.operands[0])
        targets = inst.label.split(",")
        true_label = targets[0].strip()
        false_label = targets[1].strip() if len(targets) > 1 else None

        if not _is_symbolic(cond_val):
            # Concrete condition — decide locally
            taken = bool(cond_val)
            chosen = true_label if taken else false_label
            return StateUpdate(
                next_label=chosen,
                path_condition=f"{inst.operands[0]} is {taken}",
                reasoning=f"branch_if {cond_val!r} → {chosen}",
            )
        # Symbolic condition — need LLM to decide
        return None

    if op == Opcode.BINOP:
        # %r = binop <op>, %lhs, %rhs
        oper = inst.operands[0]
        lhs = _resolve_reg(vm, inst.operands[1])
        rhs = _resolve_reg(vm, inst.operands[2])

        if not _is_symbolic(lhs) and not _is_symbolic(rhs):
            result = _eval_binop(oper, lhs, rhs)
            if result is not None:
                return StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"binop {lhs!r} {oper} {rhs!r} = {result!r}",
                )
        # Symbolic or unsupported — need LLM
        return None

    if op == Opcode.UNOP:
        # %r = unop <op>, %operand
        oper = inst.operands[0]
        operand = _resolve_reg(vm, inst.operands[1])
        if not _is_symbolic(operand):
            result = _eval_unop(oper, operand)
            if result is not None:
                return StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"unop {oper}{operand!r} = {result!r}",
                )
        return None

    # ── CALL_FUNCTION ─────────────────────────────────────────────
    if op == Opcode.CALL_FUNCTION and cfg and registry:
        func_name = inst.operands[0]
        arg_regs = inst.operands[1:]
        args = [_resolve_reg(vm, a) for a in arg_regs]

        # 1. Try builtins
        if func_name in _BUILTINS:
            result = _BUILTINS[func_name](args, vm)
            if result is not None or func_name in ("print",):
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(result)},
                    reasoning=f"builtin {func_name}({', '.join(repr(a) for a in args)}) = {result!r}",
                )

        # 2. Look up the function/class via scope chain
        func_val = None
        for f in reversed(vm.call_stack):
            if func_name in f.local_vars:
                func_val = f.local_vars[func_name]
                break
        if func_val is None:
            return None  # unknown — fall back to LLM

        # 3. Class constructor: allocate object + dispatch to __init__
        cr = _parse_class_ref(func_val)
        if cr:
            class_name, class_label = cr
            methods = registry.class_methods.get(class_name, {})
            init_label = methods.get("__init__")
            # Allocate heap object
            addr = f"obj_{vm.symbolic_counter}"
            vm.symbolic_counter += 1
            vm.heap[addr] = HeapObject(type_hint=class_name)
            if init_label and init_label in cfg.blocks:
                params = registry.func_params.get(init_label, [])
                new_vars: dict[str, Any] = {}
                # Bind self
                if params:
                    new_vars[params[0]] = addr
                # Bind remaining args to params
                for i, arg in enumerate(args):
                    if i + 1 < len(params):
                        new_vars[params[i + 1]] = _serialize_value(arg)
                return StateUpdate(
                    register_writes={inst.result_reg: addr},
                    call_push=StackFramePush(function_name=f"{class_name}.__init__",
                                             return_label=current_label),
                    next_label=init_label,
                    reasoning=f"new {class_name}({', '.join(repr(a) for a in args)}) → {addr}, dispatch __init__",
                    # We'll pre-populate local_vars via a custom mechanism
                    var_writes=new_vars,
                )
            else:
                # No __init__ — just return the new object
                return StateUpdate(
                    register_writes={inst.result_reg: addr},
                    new_objects=[NewObject(addr=addr, type_hint=class_name)],
                    reasoning=f"new {class_name}() → {addr} (no __init__)",
                )

        # 4. User-defined function: dispatch
        fr = _parse_func_ref(func_val)
        if fr:
            fname, flabel = fr
            if flabel in cfg.blocks:
                params = registry.func_params.get(flabel, [])
                new_vars = {}
                for i, arg in enumerate(args):
                    if i < len(params):
                        new_vars[params[i]] = _serialize_value(arg)
                return StateUpdate(
                    call_push=StackFramePush(function_name=fname,
                                             return_label=current_label),
                    next_label=flabel,
                    reasoning=f"call {fname}({', '.join(repr(a) for a in args)}), dispatch to {flabel}",
                    var_writes=new_vars,
                )

        return None  # unknown function — fall back to LLM

    # ── CALL_METHOD ───────────────────────────────────────────────
    if op == Opcode.CALL_METHOD and cfg and registry:
        obj_val = _resolve_reg(vm, inst.operands[0])
        method_name = inst.operands[1]
        arg_regs = inst.operands[2:]
        args = [_resolve_reg(vm, a) for a in arg_regs]

        # Resolve object type
        addr = _heap_addr(obj_val)
        type_hint = None
        if addr and addr in vm.heap:
            type_hint = vm.heap[addr].type_hint

        if type_hint and type_hint in registry.class_methods:
            methods = registry.class_methods[type_hint]
            func_label = methods.get(method_name)
            if func_label and func_label in cfg.blocks:
                params = registry.func_params.get(func_label, [])
                new_vars: dict[str, Any] = {}
                # Bind self
                if params:
                    new_vars[params[0]] = _serialize_value(obj_val)
                # Bind remaining args
                for i, arg in enumerate(args):
                    if i + 1 < len(params):
                        new_vars[params[i + 1]] = _serialize_value(arg)
                return StateUpdate(
                    call_push=StackFramePush(
                        function_name=f"{type_hint}.{method_name}",
                        return_label=current_label),
                    next_label=func_label,
                    reasoning=f"call {type_hint}.{method_name}({', '.join(repr(a) for a in args)}), dispatch to {func_label}",
                    var_writes=new_vars,
                )

        return None  # unknown method — fall back to LLM

    # Fallback — need LLM
    return None
