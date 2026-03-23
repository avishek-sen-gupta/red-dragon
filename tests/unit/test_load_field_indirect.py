"""Tests for LOAD_FIELD_INDIRECT opcode handler.

LOAD_FIELD_INDIRECT %obj %name loads a field from a heap object where
the field name comes from a register (not a static operand).  This is
needed by __method_missing__ to forward field access by dynamic name.
"""

from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.vm.vm import VMState, HeapObject, apply_update
from interpreter.vm.vm_types import StackFrame, StateUpdate, SymbolicValue
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.cfg import CFG
from interpreter.cfg_types import BasicBlock
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.types.typed_value import TypedValue, typed_from_runtime, typed, unwrap
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.constants import METHOD_MISSING


from dataclasses import replace as _replace


def _ctx(**overrides) -> HandlerContext:
    return _replace(_default_handler_context(), **overrides)


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _empty_cfg() -> CFG:
    return CFG()


def _empty_registry() -> FunctionRegistry:
    return FunctionRegistry()


def _set_reg(vm: VMState, reg: str, val: object) -> None:
    tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
    apply_update(vm, StateUpdate(register_writes={reg: tv}))


def _execute(vm: VMState, inst: IRInstruction):
    result = LocalExecutor.execute(
        inst=inst,
        vm=vm,
        ctx=_default_handler_context(),
    )
    assert result.handled
    apply_update(vm, result.update)
    return result


class TestLoadFieldIndirect:
    def test_loads_field_by_register_name(self):
        """Heap object has field 'x'=42; %name register holds 'x'. Result is 42."""
        vm = _make_vm()
        # Put an object on the heap with field x=42
        addr = "obj_0"
        vm.heap[addr] = HeapObject(
            type_hint="TestObj",
            fields={"x": typed_from_runtime(42)},
        )
        _set_reg(vm, "%obj", addr)
        _set_reg(vm, "%name", "x")

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        _execute(vm, inst)

        assert unwrap(vm.current_frame.registers["%out"]) == 42

    def test_missing_field_returns_symbolic(self):
        """Heap object exists but field 'y' is absent — result is SymbolicValue."""
        vm = _make_vm()
        addr = "obj_0"
        vm.heap[addr] = HeapObject(
            type_hint="TestObj",
            fields={"x": typed_from_runtime(42)},
        )
        _set_reg(vm, "%obj", addr)
        _set_reg(vm, "%name", "y")

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        _execute(vm, inst)

        assert isinstance(unwrap(vm.current_frame.registers["%out"]), SymbolicValue)

    def test_non_heap_object_returns_symbolic(self):
        """%obj points to an integer (not a heap address) — result is SymbolicValue."""
        vm = _make_vm()
        _set_reg(vm, "%obj", 999)
        _set_reg(vm, "%name", "x")

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        _execute(vm, inst)

        assert isinstance(unwrap(vm.current_frame.registers["%out"]), SymbolicValue)

    def test_method_missing_dispatches_function_call(self):
        """Object has __method_missing__ with BoundFuncRef — triggers call dispatch."""
        vm = _make_vm()
        addr = "obj_0"
        mm_label = CodeLabel("func_mm_0")
        mm_func_ref = FuncRef(name="__method_missing__", label=mm_label)
        mm_bound = BoundFuncRef(func_ref=mm_func_ref, closure_id="")

        vm.heap[addr] = HeapObject(
            type_hint="TestObj",
            fields={METHOD_MISSING: typed(mm_bound, UNKNOWN)},
        )
        _set_reg(vm, "%obj", addr)
        _set_reg(vm, "%name", "nonexistent")

        # CFG must contain the mm function block so _try_user_function_call succeeds
        cfg = CFG(blocks={mm_label: BasicBlock(label=mm_label)})
        registry = FunctionRegistry()
        registry.func_params[mm_label] = ["self", "name"]

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == mm_label
