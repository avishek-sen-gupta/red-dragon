"""Tests that NEW_OBJECT produces a Pointer with correct parameterized type."""

from interpreter.cfg import CFG
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import FunctionRegistry
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import Pointer, StackFrame
from interpreter.types.type_expr import pointer, scalar


from dataclasses import replace as _replace


def _ctx(**overrides) -> HandlerContext:
    return _replace(_default_handler_context(), **overrides)


def _empty_cfg_and_registry() -> tuple[CFG, FunctionRegistry]:
    return CFG(), FunctionRegistry()


class TestNewObjectPointer:
    def test_result_is_pointer(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        cfg, registry = _empty_cfg_and_registry()
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT,
            result_reg="%obj",
            operands=["Point"],
        )
        result = LocalExecutor.execute(
            inst=inst, vm=vm, ctx=_ctx(cfg=cfg, registry=registry)
        )
        assert result.handled
        tv = result.update.register_writes["%obj"]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("obj_")
        assert tv.value.offset == 0
        assert tv.type == pointer(scalar("Point"))

    def test_no_type_hint_uses_object(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        cfg, registry = _empty_cfg_and_registry()
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT,
            result_reg="%obj",
            operands=[],
        )
        result = LocalExecutor.execute(
            inst=inst, vm=vm, ctx=_ctx(cfg=cfg, registry=registry)
        )
        tv = result.update.register_writes["%obj"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Object"))
