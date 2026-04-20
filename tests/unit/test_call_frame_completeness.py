"""Tests: StackFramePush carries return_ip + result_reg so apply_update
creates a fully-initialized StackFrame without any post-patch (red-dragon-1hcq)."""

from tests.covers import covers, NotLanguageFeature
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register, NO_REGISTER
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import (
    StackFrame,
    StackFramePush,
    StateUpdate,
    VMState,
)


def _vm_with_main() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("main")))
    return vm


class TestStackFramePushCarriesCallSiteContext:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_stack_frame_push_has_return_ip_field(self):
        """StackFramePush must carry return_ip so apply_update can fully initialize the frame."""
        push = StackFramePush(
            function_name=FuncName("callee"),
            return_label=CodeLabel("block_0"),
            return_ip=3,
        )
        assert push.return_ip == 3

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_stack_frame_push_has_result_reg_field(self):
        """StackFramePush must carry result_reg so apply_update can fully initialize the frame."""
        push = StackFramePush(
            function_name=FuncName("callee"),
            result_reg=Register("%r1"),
        )
        assert push.result_reg == Register("%r1")

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_stack_frame_push_result_reg_defaults_to_no_register(self):
        """result_reg default is NO_REGISTER (no-op sentinel)."""
        push = StackFramePush(function_name=FuncName("callee"))
        assert push.result_reg == NO_REGISTER


class TestApplyUpdateCreatesCompleteFrame:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_apply_update_sets_return_ip_on_new_frame(self):
        """apply_update must propagate return_ip from StackFramePush into the new StackFrame."""
        vm = _vm_with_main()
        update = StateUpdate(
            call_push=StackFramePush(
                function_name=FuncName("callee"),
                return_label=CodeLabel("block_0"),
                return_ip=3,
            )
        )
        apply_update(vm, update)
        assert vm.current_frame.return_ip == 3

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_apply_update_sets_result_reg_on_new_frame(self):
        """apply_update must propagate result_reg from StackFramePush into the new StackFrame."""
        vm = _vm_with_main()
        update = StateUpdate(
            call_push=StackFramePush(
                function_name=FuncName("callee"),
                result_reg=Register("%r1"),
            )
        )
        apply_update(vm, update)
        assert vm.current_frame.result_reg == Register("%r1")

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_apply_update_frame_is_complete_without_post_patch(self):
        """After apply_update, new frame has return_label, return_ip, and result_reg — no patch needed."""
        vm = _vm_with_main()
        update = StateUpdate(
            call_push=StackFramePush(
                function_name=FuncName("callee"),
                return_label=CodeLabel("block_0"),
                return_ip=3,
                result_reg=Register("%r1"),
            )
        )
        apply_update(vm, update)
        frame = vm.current_frame
        assert frame.return_label == CodeLabel("block_0")
        assert frame.return_ip == 3
        assert frame.result_reg == Register("%r1")
