"""Tests for region (byte-addressed memory) VM operations.

Hand-crafted IR that allocates a region, writes bytes, reads them back.
"""

from interpreter.address import Address
from interpreter.cfg import CFG
from interpreter.ir import IRInstruction, Opcode
from interpreter.register import Register
from interpreter.registry import FunctionRegistry
from interpreter.types.typed_value import unwrap
from interpreter.vm.executor import (
    LocalExecutor,
    _default_handler_context,
)
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import SymbolicValue
from tests.unit.vm_helpers import make_vm as _make_vm


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
            result_reg=Register("%r0"),
            operands=[16],
        )
        _execute(vm, inst)

        addr_str = unwrap(vm.current_frame.registers[Register("%r0")])
        assert addr_str.startswith("rgn_")
        addr = Address(addr_str)
        assert vm.region_get(addr) is not None
        assert len(vm.region_get(addr)) == 16
        assert all(b == 0 for b in vm.region_get(addr))

    def test_alloc_symbolic_size(self):
        vm = _make_vm()
        vm.current_frame.registers[Register("%size")] = SymbolicValue(
            name="unknown_size"
        )
        inst = IRInstruction(
            opcode=Opcode.ALLOC_REGION,
            result_reg=Register("%r0"),
            operands=["%size"],
        )
        _execute(vm, inst)

        val = unwrap(vm.current_frame.registers[Register("%r0")])
        assert isinstance(val, SymbolicValue)


class TestWriteAndLoadRegion:
    def test_write_and_read_back(self):
        vm = _make_vm()

        # Allocate
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[8],
            ),
        )

        # Write [0xDE, 0xAD, 0xBE, 0xEF] at offset 2
        vm.current_frame.registers[Register("%offset")] = 2
        vm.current_frame.registers[Register("%data")] = [0xDE, 0xAD, 0xBE, 0xEF]
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
                result_reg=Register("%result"),
                operands=["%rgn", "%offset", 4],
            ),
        )

        assert unwrap(vm.current_frame.registers[Register("%result")]) == [
            0xDE,
            0xAD,
            0xBE,
            0xEF,
        ]

    def test_read_partial_region(self):
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[8],
            ),
        )

        # Write 8 bytes at offset 0
        vm.current_frame.registers[Register("%off0")] = 0
        vm.current_frame.registers[Register("%data")] = [1, 2, 3, 4, 5, 6, 7, 8]
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
                result_reg=Register("%first4"),
                operands=["%rgn", "%off0", 4],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%first4")]) == [1, 2, 3, 4]

        # Read last 4 bytes
        vm.current_frame.registers[Register("%off4")] = 4
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%last4"),
                operands=["%rgn", "%off4", 4],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%last4")]) == [5, 6, 7, 8]

    def test_load_out_of_bounds_zero_pads(self):
        """LOAD_REGION reading past the last allocated byte returns the real bytes
        and zeroes for the rest, rather than raising or truncating."""
        vm = _make_vm()

        # Allocate 4 bytes, fill with [1, 2, 3, 4]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[4],
            ),
        )
        vm.current_frame.registers[Register("%off0")] = 0
        vm.current_frame.registers[Register("%data")] = [1, 2, 3, 4]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 4, "%data"],
            ),
        )

        # Read 8 bytes from offset 0 — 4 past the region end
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%result"),
                operands=["%rgn", "%off0", 8],
            ),
        )

        # Must return exactly 8 bytes: the 4 real bytes + 4 zero bytes
        assert unwrap(vm.current_frame.registers[Register("%result")]) == [
            1,
            2,
            3,
            4,
            0,
            0,
            0,
            0,
        ]

    def test_load_past_a_region_end_reads_the_next_region(self):
        """LOAD_REGION reading past its region's end carries on into the region
        allocated after it, as storage would."""
        vm = _make_vm()
        for name, size in (("%first", 2), ("%second", 3)):
            _execute(
                vm,
                IRInstruction(
                    opcode=Opcode.ALLOC_REGION,
                    result_reg=Register(name),
                    operands=[size],
                ),
            )
        vm.current_frame.registers[Register("%off0")] = 0
        vm.current_frame.registers[Register("%data")] = [1, 2, 3, 4, 5]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%first", "%off0", 5, "%data"],
            ),
        )
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%result"),
                operands=["%first", "%off0", 4],
            ),
        )

        assert (
            unwrap(vm.current_frame.registers[Register("%result")]),
            list(
                vm.region_get(
                    Address(
                        str(unwrap(vm.current_frame.registers[Register("%second")]))
                    )
                )
                or b""
            ),
        ) == ([1, 2, 3, 4], [3, 4, 5])

    def test_load_offset_past_end_all_zeros(self):
        """LOAD_REGION entirely beyond the region end returns all zero bytes."""
        vm = _make_vm()
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[4],
            ),
        )
        vm.current_frame.registers[Register("%off")] = 8
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%result"),
                operands=["%rgn", "%off", 4],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%result")]) == [0, 0, 0, 0]

    def test_load_unknown_region_returns_symbolic(self):
        vm = _make_vm()
        vm.current_frame.registers[Register("%rgn")] = "rgn_nonexistent"
        vm.current_frame.registers[Register("%off")] = 0

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%result"),
                operands=["%rgn", "%off", 4],
            ),
        )

        val = unwrap(vm.current_frame.registers[Register("%result")])
        assert isinstance(val, SymbolicValue)

    def test_correct_bytearray_size(self):
        vm = _make_vm()
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[100],
            ),
        )

        addr = Address(unwrap(vm.current_frame.registers[Register("%rgn")]))
        assert len(vm.region_get(addr)) == 100

    def test_overwrite_partial(self):
        """Write to a region, then overwrite part of it."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg=Register("%rgn"),
                operands=[8],
            ),
        )

        # Write all 8 bytes
        vm.current_frame.registers[Register("%off0")] = 0
        vm.current_frame.registers[Register("%data1")] = [0xAA] * 8
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%data1"],
            ),
        )

        # Overwrite bytes 2-3
        vm.current_frame.registers[Register("%off2")] = 2
        vm.current_frame.registers[Register("%data2")] = [0xBB, 0xCC]
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
                result_reg=Register("%result"),
                operands=["%rgn", "%off0", 8],
            ),
        )

        expected = [0xAA, 0xAA, 0xBB, 0xCC, 0xAA, 0xAA, 0xAA, 0xAA]
        assert unwrap(vm.current_frame.registers[Register("%result")]) == expected
