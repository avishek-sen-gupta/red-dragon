"""Tests for CallWithMemory instruction, opcode, and VM handler."""

from __future__ import annotations

import pytest

from interpreter.func_name import FuncName
from interpreter.ir import Opcode
from interpreter.register import Register
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


class TestCallWithMemoryOpcode:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_with_memory_opcode_exists(self):
        assert hasattr(Opcode, "CALL_WITH_MEMORY")
        assert Opcode.CALL_WITH_MEMORY == "CALL_WITH_MEMORY"


class TestCallWithMemoryInstruction:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_instruction_carries_a_location_and_its_memory(self):
        from interpreter.instructions import CallWithMemory

        by_name = CallWithMemory(
            result_reg=Register("%r9"),
            location=VarName("__entry_SUBPROG"),
            memory=Register("%r1"),
        )
        by_register = CallWithMemory(location=Register("%r3"), memory=Register("%r1"))

        assert (
            by_name.opcode,
            by_name.operands,
            by_name.reads(),
            str(by_name),
            by_register.operands,
            by_register.reads(),
        ) == (
            Opcode.CALL_WITH_MEMORY,
            ["__entry_SUBPROG", "%r1"],
            [Register("%r1")],
            "%r9 = call_with_memory __entry_SUBPROG %r1",
            ["%r3", "%r1"],
            [Register("%r3"), Register("%r1")],
        )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_in_instruction_union(self):
        """CallWithMemory must appear in the Instruction union type."""
        import typing

        from interpreter.instructions import CallWithMemory, Instruction

        args = typing.get_args(Instruction)
        assert CallWithMemory in args


def _vm_with(bindings: dict, registers: dict):
    from interpreter.func_name import FuncName as FN
    from interpreter.types.typed_value import typed_from_runtime
    from interpreter.vm.vm_types import StackFrame, VMState

    vm = VMState()
    vm.call_stack.append(
        StackFrame(
            function_name=FN("main"),
            local_vars={name: typed_from_runtime(v) for name, v in bindings.items()},
        )
    )
    vm.current_frame.registers.update(
        {reg: typed_from_runtime(v) for reg, v in registers.items()}
    )
    return vm


def _ctx_with(label, params: list[str]):
    import dataclasses

    from interpreter.cfg import CFG, BasicBlock
    from interpreter.ir import CodeLabel
    from interpreter.registry import FunctionRegistry
    from interpreter.vm.executor import _default_handler_context

    return dataclasses.replace(
        _default_handler_context(),
        cfg=CFG(blocks={label: BasicBlock(label=label)}),
        registry=FunctionRegistry(func_params={label: params}),
        current_label=CodeLabel("caller"),
        ip=4,
    )


def _entry(label):
    from interpreter.refs.func_ref import BoundFuncRef, FuncRef

    return BoundFuncRef(func_ref=FuncRef(name=FuncName("start"), label=label))


class TestHandleCallWithMemory:
    @pytest.mark.parametrize(
        "location, registers",
        [
            (VarName("obj_start"), {}),
            (Register("%n"), {Register("%n"): "obj_start"}),
        ],
    )
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_handler_calls_the_function_registered_under_any_name(
        self, location, registers
    ):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel
        from interpreter.vm.vm_types import StackFramePush

        label = CodeLabel("func_start_0")
        vm = _vm_with(
            {VarName("obj_start"): _entry(label)},
            {**registers, Register("%m"): "memory"},
        )

        result = _handle_call_with_memory(
            CallWithMemory(
                result_reg=Register("%r"), location=location, memory=Register("%m")
            ),
            vm,
            _ctx_with(label, ["args"]),
        )
        assert (
            result.update.next_label,
            {name: tv.value for name, tv in result.update.var_writes.items()},
            result.update.call_push,
        ) == (
            label,
            {VarName("args"): "memory"},
            StackFramePush(
                function_name=FuncName("start"),
                return_label=CodeLabel("caller"),
                return_ip=5,
                result_reg=Register("%r"),
            ),
        )

    @pytest.mark.parametrize(
        "bindings",
        [{}, {VarName("obj_start"): "not a function"}],
    )
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_an_unresolved_literal_location_is_left_to_the_call_resolver(
        self, bindings
    ):
        from interpreter.handlers.calls import _handle_call_with_memory
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        vm = _vm_with(bindings, {Register("%m"): "memory"})
        result = _handle_call_with_memory(
            CallWithMemory(
                result_reg=Register("%r"),
                location=VarName("obj_start"),
                memory=Register("%m"),
            ),
            vm,
            _ctx_with(CodeLabel("func_start_0"), ["args"]),
        )

        assert (
            result.update.call_push,
            result.update.register_writes[Register("%r")].value.constraints,
        ) == (None, ["obj_start()"])

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_an_unresolved_runtime_location_raises_naming_the_variable(self):
        from interpreter.handlers.calls import (
            UnresolvedProgramError,
            _handle_call_with_memory,
        )
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        vm = _vm_with({}, {Register("%n"): "obj_missing", Register("%m"): "memory"})

        with pytest.raises(UnresolvedProgramError, match="obj_missing"):
            _handle_call_with_memory(
                CallWithMemory(location=Register("%n"), memory=Register("%m")),
                vm,
                _ctx_with(CodeLabel("func_start_0"), ["args"]),
            )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_a_callee_that_declares_no_parameter_cannot_receive_memory(self):
        from interpreter.handlers.calls import (
            MemoryNotReceivedError,
            _handle_call_with_memory,
        )
        from interpreter.instructions import CallWithMemory
        from interpreter.ir import CodeLabel

        label = CodeLabel("func_start_0")
        vm = _vm_with({VarName("obj_start"): _entry(label)}, {Register("%m"): "memory"})

        with pytest.raises(MemoryNotReceivedError, match="func_start_0"):
            _handle_call_with_memory(
                CallWithMemory(location=VarName("obj_start"), memory=Register("%m")),
                vm,
                _ctx_with(label, []),
            )
