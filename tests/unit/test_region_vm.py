"""Tests for region (byte-addressed memory) VM operations.

Hand-crafted IR that allocates a region, writes bytes, reads them back.
"""

from interpreter.ir import IRInstruction, Opcode
from interpreter.vm.vm import VMState, apply_update
from interpreter.types.typed_value import unwrap
from interpreter.vm.vm_types import StackFrame, SymbolicValue
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
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
        ctx=_default_handler_context(),
    )
    assert result.handled
    apply_update(vm, result.update)
    return result


class TestAllocRegion:
    def test_alloc_creates_region(self):
        vm = _make_vm()
        inst = IRInstruction(
            opcode=Opcode.ALLOC_REGION,
            result_reg="%r0",
            operands=[16],
        )
        _execute(vm, inst)

        addr = unwrap(vm.current_frame.registers["%r0"])
        assert addr.startswith("rgn_")
        assert addr in vm.regions
        assert len(vm.regions[addr]) == 16
        assert all(b == 0 for b in vm.regions[addr])

    def test_alloc_symbolic_size(self):
        vm = _make_vm()
        vm.current_frame.registers["%size"] = SymbolicValue(name="unknown_size")
        inst = IRInstruction(
            opcode=Opcode.ALLOC_REGION,
            result_reg="%r0",
            operands=["%size"],
        )
        _execute(vm, inst)

        val = unwrap(vm.current_frame.registers["%r0"])
        assert isinstance(val, SymbolicValue)


class TestWriteAndLoadRegion:
    def test_write_and_read_back(self):
        vm = _make_vm()

        # Allocate
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        # Write [0xDE, 0xAD, 0xBE, 0xEF] at offset 2
        vm.current_frame.registers["%offset"] = 2
        vm.current_frame.registers["%data"] = [0xDE, 0xAD, 0xBE, 0xEF]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%offset", 4, "%data"],
            ),
        )

        # Read back 4 bytes from offset 2
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%result",
                operands=["%rgn", "%offset", 4],
            ),
        )

        assert unwrap(vm.current_frame.registers["%result"]) == [0xDE, 0xAD, 0xBE, 0xEF]

    def test_read_partial_region(self):
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        # Write 8 bytes at offset 0
        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%data"] = [1, 2, 3, 4, 5, 6, 7, 8]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%data"],
            ),
        )

        # Read first 4 bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%first4",
                operands=["%rgn", "%off0", 4],
            ),
        )
        assert unwrap(vm.current_frame.registers["%first4"]) == [1, 2, 3, 4]

        # Read last 4 bytes
        vm.current_frame.registers["%off4"] = 4
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%last4",
                operands=["%rgn", "%off4", 4],
            ),
        )
        assert unwrap(vm.current_frame.registers["%last4"]) == [5, 6, 7, 8]

    def test_load_unknown_region_returns_symbolic(self):
        vm = _make_vm()
        vm.current_frame.registers["%rgn"] = "rgn_nonexistent"
        vm.current_frame.registers["%off"] = 0

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%result",
                operands=["%rgn", "%off", 4],
            ),
        )

        val = unwrap(vm.current_frame.registers["%result"])
        assert isinstance(val, SymbolicValue)

    def test_correct_bytearray_size(self):
        vm = _make_vm()
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[100],
            ),
        )

        addr = unwrap(vm.current_frame.registers["%rgn"])
        assert len(vm.regions[addr]) == 100

    def test_overwrite_partial(self):
        """Write to a region, then overwrite part of it."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        # Write all 8 bytes
        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%data1"] = [0xAA] * 8
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%data1"],
            ),
        )

        # Overwrite bytes 2-3
        vm.current_frame.registers["%off2"] = 2
        vm.current_frame.registers["%data2"] = [0xBB, 0xCC]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off2", 2, "%data2"],
            ),
        )

        # Read all 8 bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%result",
                operands=["%rgn", "%off0", 8],
            ),
        )

        expected = [0xAA, 0xAA, 0xBB, 0xCC, 0xAA, 0xAA, 0xAA, 0xAA]
        assert unwrap(vm.current_frame.registers["%result"]) == expected
