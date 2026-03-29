"""Unit tests for CALL_METHOD resolving methods from heap object fields.

When a method is stored as a field on a heap object (e.g., Lua table OOP,
JS dynamic property assignment), CALL_METHOD should find and invoke it
rather than falling back to symbolic resolution.
"""

from __future__ import annotations

from interpreter.field_name import FieldName
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.vm.vm import VMState, SymbolicValue, apply_update
from interpreter.address import Address
from interpreter.vm.vm_types import HeapObject, Pointer, StackFrame
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.cfg import CFG, build_cfg
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.types.typed_value import typed, typed_from_runtime, unwrap
from interpreter.types.type_expr import scalar, UNKNOWN
from interpreter.constants import TypeName
from interpreter.register import Register


from dataclasses import replace as _replace


def _ctx(**overrides) -> HandlerContext:
    return _replace(_default_handler_context(), **overrides)


def _build_callable_field_vm():
    """Build a VM with a heap object whose 'greet' field is a BoundFuncRef.

    The function body is: return the first parameter (identity function).
    """
    instructions = [
        IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
        IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("__func__greet")),
        IRInstruction(
            opcode=Opcode.RETURN,
            operands=["%param_self", "%param_x"],
            result_reg="%ret",
        ),
    ]
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    registry.func_params["__func__greet"] = ["self", "x"]

    vm = VMState()
    func_ref = FuncRef(name="greet", label=CodeLabel("__func__greet"))
    bound = BoundFuncRef(func_ref=func_ref, closure_id="")

    vm.heap["obj_0"] = HeapObject(
        type_hint="table",
        fields={
            FieldName("greet"): typed_from_runtime(bound),
        },
    )
    ptr = Pointer(base=Address("obj_0"), offset=0)
    vm.call_stack.append(
        StackFrame(
            function_name="<main>",
            registers={Register("%obj"): typed_from_runtime(ptr)},
        )
    )
    return vm, cfg, registry


class TestHeapFieldMethodCall:
    def test_call_method_finds_field_callable(self):
        """CALL_METHOD on an object with a callable field should dispatch
        to the function (push a frame), not produce a symbolic value."""
        vm, cfg, registry = _build_callable_field_vm()
        vm.current_frame.registers[Register("%arg")] = typed_from_runtime(42)
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "greet", "%obj", "%arg"],
        )
        result = LocalExecutor.execute(
            inst=inst, vm=vm, ctx=_ctx(cfg=cfg, registry=registry)
        )
        assert result.handled
        assert (
            result.update.call_push is not None
        ), "Expected function dispatch (call_push), got register write (symbolic)"
        assert result.update.call_push.function_name == "greet"

    def test_call_method_field_not_callable_falls_back(self):
        """CALL_METHOD on a field that's not callable should fall back to resolver."""
        vm, cfg, registry = _build_callable_field_vm()
        # Overwrite greet with a non-callable value
        vm.heap["obj_0"].fields[FieldName("greet")] = typed_from_runtime(42)
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "greet", "%obj"],
        )
        result = LocalExecutor.execute(
            inst=inst, vm=vm, ctx=_ctx(cfg=cfg, registry=registry)
        )
        assert result.handled
        assert result.update.call_push is None, "Should fall back, not dispatch"
        assert isinstance(
            result.update.register_writes[Register("%result")].value, SymbolicValue
        )

    def test_call_method_missing_field_falls_back(self):
        """CALL_METHOD for a method not in fields should fall back to resolver."""
        vm, cfg, registry = _build_callable_field_vm()
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "nonexistent", "%obj"],
        )
        result = LocalExecutor.execute(
            inst=inst, vm=vm, ctx=_ctx(cfg=cfg, registry=registry)
        )
        assert result.handled
        assert result.update.call_push is None, "Should fall back, not dispatch"
        assert isinstance(
            result.update.register_writes[Register("%result")].value, SymbolicValue
        )
