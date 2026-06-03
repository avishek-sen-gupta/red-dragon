"""Tests for CallWithMemory instruction, opcode, and VM handler."""

from __future__ import annotations

import pytest
from interpreter.func_name import FuncName, NO_FUNC_NAME
from interpreter.register import Register, NO_REGISTER
from interpreter.ir import Opcode
from interpreter.var_name import VarName
from tests.covers import covers, NotLanguageFeature


class TestCallWithMemoryOpcode:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_with_memory_opcode_exists(self):
        assert hasattr(Opcode, "CALL_WITH_MEMORY")
        assert Opcode.CALL_WITH_MEMORY == "CALL_WITH_MEMORY"


class TestCallWithMemoryInstruction:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_instruction_fields(self):
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        assert inst.func_name == FuncName("SUBPROG")
        assert inst.params_reg == Register("%r1")
        assert inst.results_reg == Register("%r2")
        assert inst.opcode == Opcode.CALL_WITH_MEMORY

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_instruction_defaults(self):
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory()
        assert inst.func_name == NO_FUNC_NAME
        assert inst.params_reg == NO_REGISTER
        assert inst.results_reg == NO_REGISTER

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_operands(self):
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        ops = inst.operands
        assert "SUBPROG" in ops
        assert "%r1" in ops
        assert "%r2" in ops

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_reads_both_regs(self):
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        reads = inst.reads()
        assert Register("%r1") in reads
        assert Register("%r2") in reads

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_reads_deduplicates_same_reg(self):
        """When params_reg == results_reg, reads() should not duplicate it."""
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r1"),
        )
        reads = inst.reads()
        assert reads.count(Register("%r1")) == 1

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_in_instruction_union(self):
        """CallWithMemory must appear in the Instruction union type."""
        import typing
        from interpreter.instructions import CallWithMemory, Instruction

        args = typing.get_args(Instruction)
        assert CallWithMemory in args


# ── Handler tests ────────────────────────────────────────────────


def _make_vm_with_func_ref(callee_label: str, func_name: str, params_val, results_val):
    """Build a minimal VMState with a BoundFuncRef in scope and two region registers."""
    from interpreter.vm.vm_types import VMState, StackFrame
    from interpreter.func_name import FuncName as FN
    from interpreter.var_name import VarName as VN
    from interpreter.refs.func_ref import FuncRef, BoundFuncRef
    from interpreter.types.typed_value import typed_from_runtime
    from interpreter.register import Register as Reg
    from interpreter.ir import CodeLabel

    vm = VMState()
    frame = StackFrame(function_name=FN("CALLER"))
    frame.local_vars[VN(func_name)] = typed_from_runtime(
        BoundFuncRef(
            func_ref=FuncRef(name=FN(func_name), label=CodeLabel(callee_label))
        )
    )
    frame.registers[Reg("%r1")] = typed_from_runtime(params_val)
    frame.registers[Reg("%r2")] = typed_from_runtime(results_val)
    vm.call_stack.append(frame)
    return vm


def _make_handler_ctx(callee_label: str):
    """Build a minimal HandlerContext with the callee block in the CFG."""
    import dataclasses
    from interpreter.vm.executor import _default_handler_context
    from interpreter.cfg import CFG, BasicBlock
    from interpreter.ir import NO_LABEL, CodeLabel

    cfg = CFG()
    lbl = CodeLabel(callee_label)
    cfg.blocks[lbl] = BasicBlock(label=lbl)
    ctx = _default_handler_context()
    ctx = dataclasses.replace(ctx, cfg=cfg, current_label=NO_LABEL)
    return ctx


class TestHandleCallWithMemory:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_returns_handled(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(
            callee_label, "SUBPROG", {"region": "params"}, {"region": "results"}
        )
        ctx = _make_handler_ctx(callee_label)

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        result = _handle_call_with_memory(inst, vm, ctx)

        assert result.handled

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_sets_next_label_to_callee(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(
            callee_label, "SUBPROG", {"region": "params"}, {"region": "results"}
        )
        ctx = _make_handler_ctx(callee_label)

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        result = _handle_call_with_memory(inst, vm, ctx)

        assert result.update.next_label == callee_label

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_injects_params_region_var(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(
            callee_label, "SUBPROG", {"region": "params"}, {"region": "results"}
        )
        ctx = _make_handler_ctx(callee_label)

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        result = _handle_call_with_memory(inst, vm, ctx)

        assert VarName("__params_region") in result.update.var_writes

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_injects_results_region_var(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(
            callee_label, "SUBPROG", {"region": "params"}, {"region": "results"}
        )
        ctx = _make_handler_ctx(callee_label)

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        result = _handle_call_with_memory(inst, vm, ctx)

        assert VarName("__results_region") in result.update.var_writes

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_pushes_call_frame(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(
            callee_label, "SUBPROG", {"region": "params"}, {"region": "results"}
        )
        ctx = _make_handler_ctx(callee_label)

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            results_reg=Register("%r2"),
        )
        result = _handle_call_with_memory(inst, vm, ctx)

        assert result.update.call_push is not None
