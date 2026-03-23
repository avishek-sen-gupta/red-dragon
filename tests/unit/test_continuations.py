"""Tests for continuation opcodes — SET_CONTINUATION and RESUME_CONTINUATION."""

from interpreter.cfg import build_cfg
from interpreter.vm.executor import (
    _handle_resume_continuation,
    _handle_set_continuation,
    _default_handler_context,
)

_CTX = _default_handler_context()
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.vm.vm import VMState, apply_update
from interpreter.vm.vm_types import StackFrame, StateUpdate


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


class TestHandleSetContinuation:
    def test_produces_correct_state_update(self):
        inst = IRInstruction(
            opcode=Opcode.SET_CONTINUATION,
            operands=["para_WORK_end", CodeLabel("perform_return_0")],
        )
        vm = _make_vm()
        result = _handle_set_continuation(inst, vm, _CTX)

        assert result.handled
        assert result.update.continuation_writes == {
            "para_WORK_end": "perform_return_0"
        }

    def test_last_writer_wins(self):
        """Second SET_CONTINUATION overwrites the first for the same name."""
        vm = _make_vm()

        inst1 = IRInstruction(
            opcode=Opcode.SET_CONTINUATION,
            operands=["para_X_end", CodeLabel("return_A")],
        )
        result1 = _handle_set_continuation(inst1, vm, _CTX)
        apply_update(vm, result1.update)
        assert vm.continuations["para_X_end"] == "return_A"

        inst2 = IRInstruction(
            opcode=Opcode.SET_CONTINUATION,
            operands=["para_X_end", CodeLabel("return_B")],
        )
        result2 = _handle_set_continuation(inst2, vm, _CTX)
        apply_update(vm, result2.update)
        assert vm.continuations["para_X_end"] == "return_B"


class TestHandleResumeContinuation:
    def test_branches_when_set(self):
        vm = _make_vm()
        vm.continuations["para_WORK_end"] = CodeLabel("perform_return_0")

        inst = IRInstruction(
            opcode=Opcode.RESUME_CONTINUATION,
            operands=["para_WORK_end"],
        )
        result = _handle_resume_continuation(inst, vm, _CTX)

        assert result.handled
        assert result.update.next_label == "perform_return_0"
        assert result.update.continuation_clear == "para_WORK_end"

    def test_falls_through_when_not_set(self):
        vm = _make_vm()

        inst = IRInstruction(
            opcode=Opcode.RESUME_CONTINUATION,
            operands=["para_WORK_end"],
        )
        result = _handle_resume_continuation(inst, vm, _CTX)

        assert result.handled
        assert result.update.next_label is None
        assert result.update.continuation_clear == "para_WORK_end"


class TestApplyUpdateContinuations:
    def test_writes_continuation(self):
        vm = _make_vm()
        update = StateUpdate(
            continuation_writes={"para_X_end": CodeLabel("return_label")},
            reasoning="test",
        )
        apply_update(vm, update)
        assert vm.continuations["para_X_end"] == "return_label"

    def test_clears_continuation(self):
        vm = _make_vm()
        vm.continuations["para_X_end"] = CodeLabel("return_label")

        update = StateUpdate(continuation_clear="para_X_end", reasoning="test")
        apply_update(vm, update)
        assert "para_X_end" not in vm.continuations

    def test_clear_nonexistent_is_noop(self):
        vm = _make_vm()
        update = StateUpdate(continuation_clear="para_NONEXIST_end", reasoning="test")
        apply_update(vm, update)
        assert "para_NONEXIST_end" not in vm.continuations


class TestCFGBuilderResumeContinuation:
    def test_resume_continuation_terminates_block(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("para_A")),
            IRInstruction(opcode=Opcode.CONST, result_reg="%r0", operands=["hello"]),
            IRInstruction(
                opcode=Opcode.RESUME_CONTINUATION,
                operands=["para_A_end"],
            ),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("para_B")),
            IRInstruction(opcode=Opcode.CONST, result_reg="%r1", operands=["world"]),
            IRInstruction(
                opcode=Opcode.RESUME_CONTINUATION,
                operands=["para_B_end"],
            ),
        ]
        cfg = build_cfg(instructions)

        assert "para_A" in cfg.blocks
        assert "para_B" in cfg.blocks

        # para_A should have a fall-through edge to para_B
        assert "para_B" in cfg.blocks["para_A"].successors

    def test_resume_continuation_gets_diamond_shape(self):
        """RESUME_CONTINUATION blocks should render with diamond (conditional) shape in Mermaid."""
        from interpreter.cfg import _node_shape
        from interpreter.cfg_types import BasicBlock

        block = BasicBlock(
            label=CodeLabel("para_A"),
            instructions=[
                IRInstruction(
                    opcode=Opcode.RESUME_CONTINUATION,
                    operands=["para_A_end"],
                ),
            ],
        )
        open_delim, close_delim = _node_shape(block, is_entry=False)
        assert open_delim == '{"'
        assert close_delim == '"}'
