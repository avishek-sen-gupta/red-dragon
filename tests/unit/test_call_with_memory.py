"""Tests for CallWithMemory instruction, opcode, and VM handler."""

from __future__ import annotations

from interpreter.func_name import NO_FUNC_NAME, FuncName
from interpreter.ir import Opcode
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


class TestCallWithMemoryOpcode:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_with_memory_opcode_exists(self):
        assert hasattr(Opcode, "CALL_WITH_MEMORY")
        assert Opcode.CALL_WITH_MEMORY == "CALL_WITH_MEMORY"


class TestCallWithMemoryInstruction:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_instruction_carries_the_callee_and_its_argument_array(self):
        from interpreter.instructions import CallWithMemory

        inst = CallWithMemory(
            func_name=FuncName("SUBPROG"),
            params_reg=Register("%r1"),
            target_reg=Register("%r3"),
        )
        defaults = CallWithMemory()

        assert (
            inst.opcode,
            inst.operands,
            inst.reads(),
            defaults.func_name,
            defaults.params_reg,
            defaults.operands,
        ) == (
            Opcode.CALL_WITH_MEMORY,
            ["SUBPROG", "%r1", "%r3"],
            [Register("%r1"), Register("%r3")],
            NO_FUNC_NAME,
            NO_REGISTER,
            [str(NO_FUNC_NAME), str(NO_REGISTER)],
        )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_in_instruction_union(self):
        """CallWithMemory must appear in the Instruction union type."""
        import typing

        from interpreter.instructions import CallWithMemory, Instruction

        args = typing.get_args(Instruction)
        assert CallWithMemory in args


# ── Handler tests ────────────────────────────────────────────────


def _make_vm_with_func_ref(callee_label: str, func_name: str, params_val):
    """Build a minimal VMState with a singleton HeapObject in scope and the
    argument array in %r1.

    Updated for singleton dispatch: stores __prog_<FUNCNAME> singleton with
    __init_params__ BoundFuncRef pointing at callee_label.
    """
    from interpreter.address import Address
    from interpreter.field_name import FieldName
    from interpreter.func_name import FuncName as FN
    from interpreter.ir import CodeLabel
    from interpreter.refs.func_ref import BoundFuncRef, FuncRef
    from interpreter.register import Register as Reg
    from interpreter.types.typed_value import typed_from_runtime
    from interpreter.var_name import VarName as VN
    from interpreter.vm.vm_types import HeapObject, StackFrame, VMState

    vm = VMState()
    frame = StackFrame(function_name=FN("CALLER"))

    # Build singleton HeapObject with __init_params__ pointing at callee_label
    init_params_ref = BoundFuncRef(
        func_ref=FuncRef(name=FN(func_name), label=CodeLabel(callee_label))
    )
    singleton = HeapObject(
        fields={
            FieldName("__init_params__"): typed_from_runtime(init_params_ref),
        }
    )
    singleton_addr = Address("obj_singleton")
    vm._heap[singleton_addr] = singleton
    frame.local_vars[VN(f"__prog_{func_name.upper()}")] = typed_from_runtime(
        singleton_addr
    )

    frame.registers[Reg("%r1")] = typed_from_runtime(params_val)
    vm.call_stack.append(frame)
    return vm


def _make_handler_ctx(callee_label: str):
    """Build a minimal HandlerContext with the callee block in the CFG."""
    import dataclasses

    from interpreter.cfg import CFG, BasicBlock
    from interpreter.ir import NO_LABEL, CodeLabel
    from interpreter.vm.executor import _default_handler_context

    cfg = CFG()
    lbl = CodeLabel(callee_label)
    cfg.blocks[lbl] = BasicBlock(label=lbl)
    ctx = _default_handler_context()
    ctx = dataclasses.replace(ctx, cfg=cfg, current_label=NO_LABEL)
    return ctx


class TestHandleCallWithMemory:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_dispatches_to_the_callee_with_the_argument_array(self):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory

        callee_label = "func_SUBPROG"
        vm = _make_vm_with_func_ref(callee_label, "SUBPROG", "arr_7")
        ctx = _make_handler_ctx(callee_label)

        result = _handle_call_with_memory(
            CallWithMemory(func_name=FuncName("SUBPROG"), params_reg=Register("%r1")),
            vm,
            ctx,
        )

        assert (
            result.handled,
            result.update.next_label,
            {name: tv.value for name, tv in result.update.var_writes.items()},
            result.update.call_push.function_name,
        ) == (
            True,
            callee_label,
            {VarName("__call_arguments"): "arr_7"},
            FuncName("SUBPROG"),
        )
