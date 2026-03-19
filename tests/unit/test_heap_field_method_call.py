"""Unit tests for CALL_METHOD resolving methods from heap object fields.

When a method is stored as a field on a heap object (e.g., Lua table OOP,
JS dynamic property assignment), CALL_METHOD should find and invoke it
rather than falling back to symbolic resolution.
"""

from __future__ import annotations

from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState, SymbolicValue, apply_update
from interpreter.vm_types import HeapObject, Pointer, StackFrame
from interpreter.executor import LocalExecutor
from interpreter.cfg import CFG, build_cfg
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.func_ref import FuncRef, BoundFuncRef
from interpreter.typed_value import typed, typed_from_runtime, unwrap
from interpreter.type_expr import scalar, UNKNOWN
from interpreter.constants import TypeName


def _build_callable_field_vm():
    """Build a VM with a heap object whose 'greet' field is a BoundFuncRef.

    The function body is: return the first parameter (identity function).
    """
    instructions = [
        IRInstruction(opcode=Opcode.LABEL, label="entry"),
        IRInstruction(opcode=Opcode.LABEL, label="__func__greet"),
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
    func_ref = FuncRef(name="greet", label="__func__greet")
    bound = BoundFuncRef(func_ref=func_ref, closure_id="")

    vm.heap["obj_0"] = HeapObject(
        type_hint="table",
        fields={
            "greet": typed_from_runtime(bound),
        },
    )
    ptr = Pointer(base="obj_0", offset=0)
    vm.call_stack.append(
        StackFrame(
            function_name="<main>",
            registers={"%obj": typed_from_runtime(ptr)},
        )
    )
    return vm, cfg, registry


class TestHeapFieldMethodCall:
    def test_call_method_finds_field_callable(self):
        """CALL_METHOD on an object with a callable field should dispatch
        to the function (push a frame), not produce a symbolic value."""
        vm, cfg, registry = _build_callable_field_vm()
        vm.current_frame.registers["%arg"] = typed_from_runtime(42)
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "greet", "%obj", "%arg"],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm, cfg=cfg, registry=registry)
        assert result.handled
        assert (
            result.update.call_push is not None
        ), "Expected function dispatch (call_push), got register write (symbolic)"
        assert result.update.call_push.function_name == "greet"

    def test_call_method_field_not_callable_falls_back(self):
        """CALL_METHOD on a field that's not callable should fall back to resolver."""
        vm, cfg, registry = _build_callable_field_vm()
        # Overwrite greet with a non-callable value
        vm.heap["obj_0"].fields["greet"] = typed_from_runtime(42)
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "greet", "%obj"],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm, cfg=cfg, registry=registry)
        assert result.handled  # falls back to symbolic, still handled

    def test_call_method_missing_field_falls_back(self):
        """CALL_METHOD for a method not in fields should fall back to resolver."""
        vm, cfg, registry = _build_callable_field_vm()
        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%result",
            operands=["%obj", "nonexistent", "%obj"],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm, cfg=cfg, registry=registry)
        assert result.handled  # falls back to symbolic, still handled
