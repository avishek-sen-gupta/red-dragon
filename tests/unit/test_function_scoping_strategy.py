# tests/unit/test_function_scoping_strategy.py
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from interpreter.types.typed_value import TypedValue, typed
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName
from interpreter.vm.function_scoping import (
    GlobalLeakFunctionScopingStrategy,
    LocalFunctionScopingStrategy,
)
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import StackFrame
from interpreter.func_name import FuncName
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel
from interpreter.handlers._common import _write_var_to_frame
from interpreter.vm.executor import HandlerContext, _default_handler_context


def _make_func_ref_value() -> TypedValue:
    ref = FuncRef(name=FuncName("inner"), label=CodeLabel("func_inner"))
    return typed(ref, scalar("function"))


def _make_vm_with_depth(depth: int) -> tuple[VMState, StackFrame]:
    """Create a VMState with `depth` frames. Returns (vm, top_frame)."""
    vm = VMState()
    vm.call_stack = [
        StackFrame(function_name=FuncName(f"frame_{i}")) for i in range(depth)
    ]
    return vm, vm.call_stack[-1]


NAME = VarName("inner")


class TestLocalFunctionScopingStrategy:
    def test_writes_to_current_frame_at_depth_1(self):
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        LocalFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value

    def test_does_not_write_to_global_frame_at_depth_2(self):
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        LocalFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert NAME not in vm.call_stack[0].local_vars


class TestGlobalLeakFunctionScopingStrategy:
    def test_writes_to_current_frame_at_depth_1(self):
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value

    def test_no_double_write_at_depth_1(self):
        """current_frame IS global frame at depth 1 — only one write."""
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert vm.call_stack[0].local_vars[NAME] == value
        # value written exactly once (same object)
        assert frame is vm.call_stack[0]

    def test_writes_to_both_frames_at_depth_2(self):
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert vm.call_stack[0].local_vars[NAME] == value

    def test_writes_to_both_frames_at_depth_3(self):
        vm, frame = _make_vm_with_depth(3)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert vm.call_stack[0].local_vars[NAME] == value


class TestWriteVarToFrameDelegation:
    def test_funcref_written_to_global_frame_via_strategy(self):
        """_write_var_to_frame must call the strategy for FuncRef values."""
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        default_ctx = _default_handler_context()
        ctx = HandlerContext(
            cfg=default_ctx.cfg,
            registry=default_ctx.registry,
            current_label=default_ctx.current_label,
            ip=default_ctx.ip,
            call_resolver=default_ctx.call_resolver,
            overload_resolver=default_ctx.overload_resolver,
            type_env=default_ctx.type_env,
            binop_coercion=default_ctx.binop_coercion,
            unop_coercion=default_ctx.unop_coercion,
            func_symbol_table=default_ctx.func_symbol_table,
            class_symbol_table=default_ctx.class_symbol_table,
            field_fallback=default_ctx.field_fallback,
            symbol_table=default_ctx.symbol_table,
            function_scoping=GlobalLeakFunctionScopingStrategy(),
        )
        _write_var_to_frame(vm, frame, NAME, value, ctx)
        assert vm.call_stack[0].local_vars[NAME] == value

    def test_non_funcref_not_delegated_to_strategy(self):
        """Plain values bypass the strategy entirely."""
        vm, frame = _make_vm_with_depth(2)
        plain = typed(42, scalar("int"))
        ctx = _default_handler_context()
        _write_var_to_frame(vm, frame, NAME, plain, ctx)
        assert frame.local_vars[NAME] == plain
        assert NAME not in vm.call_stack[0].local_vars
