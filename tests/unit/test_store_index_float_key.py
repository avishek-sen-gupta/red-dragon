"""Tests proving the float-index heap key mismatch bug.

When STORE_INDEX receives a float index (e.g. 2.0) it writes to heap key "2.0".
When LOAD_INDEX receives an int index (e.g. 2) it looks up heap key "2".
These keys don't match, so the stored value is silently lost.
"""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import StackFrame
from interpreter.executor import LocalExecutor
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _empty_cfg() -> CFG:
    return CFG()


def _empty_registry() -> FunctionRegistry:
    return FunctionRegistry()


def _execute(vm, inst):
    result = LocalExecutor.execute(
        inst=inst,
        vm=vm,
        cfg=_empty_cfg(),
        registry=_empty_registry(),
    )
    assert result.handled
    apply_update(vm, result.update)
    return result


def _setup_array(vm):
    """Create a NEW_ARRAY on the heap and return the vm with %arr set."""
    _execute(
        vm,
        IRInstruction(
            opcode=Opcode.NEW_ARRAY,
            result_reg="%arr",
            operands=["int"],
        ),
    )
    return vm


class TestFloatIndexHeapKeyMismatch:
    @pytest.mark.xfail(
        reason="Bug: float store key '2.0' != int load key '2'", strict=True
    )
    def test_float_store_int_load_reads_back_stored_value(self):
        """STORE_INDEX with float 2.0, then LOAD_INDEX with int 2 — value should round-trip."""
        vm = _setup_array(_make_vm())

        # Store value 42 at float index 2.0
        vm.current_frame.registers["%idx_f"] = 2.0
        vm.current_frame.registers["%val"] = 42
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_f", "%val"],
            ),
        )

        # Load from int index 2
        vm.current_frame.registers["%idx_i"] = 2
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%out",
                operands=["%arr", "%idx_i"],
            ),
        )

        assert vm.current_frame.registers["%out"] == 42

    @pytest.mark.xfail(
        reason="Bug: int store key '2' != float load key '2.0'", strict=True
    )
    def test_int_store_float_load_reads_back_stored_value(self):
        """STORE_INDEX with int 2, then LOAD_INDEX with float 2.0 — value should round-trip."""
        vm = _setup_array(_make_vm())

        # Store value 99 at int index 2
        vm.current_frame.registers["%idx_i"] = 2
        vm.current_frame.registers["%val"] = 99
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_i", "%val"],
            ),
        )

        # Load from float index 2.0
        vm.current_frame.registers["%idx_f"] = 2.0
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%out",
                operands=["%arr", "%idx_f"],
            ),
        )

        assert vm.current_frame.registers["%out"] == 99

    def test_heap_key_written_by_float_index(self):
        """After STORE_INDEX with float 2.0, heap key is '2.0' not '2' — proves root cause."""
        vm = _setup_array(_make_vm())

        vm.current_frame.registers["%idx_f"] = 2.0
        vm.current_frame.registers["%val"] = 77
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_f", "%val"],
            ),
        )

        arr_addr = vm.current_frame.registers["%arr"]
        heap_obj = vm.heap[arr_addr]
        assert "2.0" in heap_obj.fields, "Expected float key '2.0' in heap fields"
        assert (
            "2" not in heap_obj.fields
        ), "Key '2' should NOT exist — only '2.0' was written"
