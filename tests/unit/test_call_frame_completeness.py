"""Tests: a call handler emits a complete StackFramePush, and apply_update builds the frame from it."""

from dataclasses import replace

from interpreter.address import Address
from interpreter.cfg import build_cfg
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel, IRInstruction, Opcode
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.register import Register
from interpreter.registry import build_registry
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.executor import LocalExecutor, _default_handler_context
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import (
    HeapObject,
    Pointer,
    StackFrame,
    StackFramePush,
    StateUpdate,
    VMState,
)
from tests.covers import NotLanguageFeature, covers


def _vm_with_main() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("main")))
    return vm


class TestCallFrameCompleteness:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_handler_emits_the_call_site_in_its_push(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("__func__greet")),
            IRInstruction(opcode=Opcode.RETURN, operands=["%param_self"]),
        ]
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)
        registry.func_params["__func__greet"] = ["self"]
        vm = VMState()
        greet = BoundFuncRef(
            func_ref=FuncRef(name=FuncName("greet"), label=CodeLabel("__func__greet"))
        )
        vm.heap_set(
            Address("obj_0"),
            HeapObject(
                type_hint="table",
                fields={FieldName("greet"): typed_from_runtime(greet)},
            ),
        )
        vm.call_stack.append(
            StackFrame(
                function_name=FuncName("<main>"),
                registers={
                    Register("%obj"): typed_from_runtime(
                        Pointer(base=Address("obj_0"), offset=0)
                    )
                },
            )
        )
        ctx = replace(
            _default_handler_context(),
            cfg=cfg,
            registry=registry,
            current_label=CodeLabel("entry"),
            ip=4,
        )

        result = LocalExecutor.execute(
            inst=IRInstruction(
                opcode=Opcode.CALL_METHOD,
                result_reg=Register("%result"),
                operands=["%obj", "greet", "%obj"],
            ),
            vm=vm,
            ctx=ctx,
        )

        assert result.update.call_push == StackFramePush(
            function_name=FuncName("greet"),
            return_label=CodeLabel("entry"),
            return_ip=5,
            result_reg=Register("%result"),
        )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_apply_update_builds_the_frame_from_the_push(self):
        vm = _vm_with_main()
        apply_update(
            vm,
            StateUpdate(
                call_push=StackFramePush(
                    function_name=FuncName("callee"),
                    return_label=CodeLabel("block_0"),
                    return_ip=3,
                    result_reg=Register("%r1"),
                )
            ),
        )
        frame = vm.current_frame
        assert (
            frame.function_name,
            frame.return_label,
            frame.return_ip,
            frame.result_reg,
        ) == (FuncName("callee"), CodeLabel("block_0"), 3, Register("%r1"))
