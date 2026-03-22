"""End-to-end REDEFINES tests using hand-crafted IR.

Tests the full stack: IR encoder/decoder functions → builtins → region ops.
Each test allocates a region, encodes/writes data, reads overlapping bytes,
and decodes — validating COBOL REDEFINES byte-overlay semantics.
"""

from typing import Any

from interpreter.ir import IRInstruction, Opcode
from interpreter.types.typed_value import unwrap
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import StackFrame
from interpreter.executor import LocalExecutor, HandlerContext, _default_handler_context
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry

from interpreter.cobol.ir_encoders import (
    build_encode_zoned_ir,
    build_decode_zoned_ir,
    build_encode_alphanumeric_ir,
    build_decode_alphanumeric_ir,
)
from interpreter.cobol.data_filters import align_decimal, left_adjust


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _execute(vm: VMState, inst: IRInstruction) -> Any:
    """Execute a single instruction and apply its update."""
    result = LocalExecutor.execute(inst=inst, vm=vm, ctx=_default_handler_context())
    assert result.handled, f"Instruction not handled: {inst}"
    apply_update(vm, result.update)
    return result


def _execute_ir_sequence(vm: VMState, instructions: list[IRInstruction]) -> Any:
    """Execute a sequence of IR instructions, return the RETURN value."""
    for inst in instructions:
        if inst.opcode == Opcode.LABEL:
            continue
        result = LocalExecutor.execute(inst=inst, vm=vm, ctx=_default_handler_context())
        assert result.handled, f"Instruction not handled: {inst}"
        apply_update(vm, result.update)
        if inst.opcode == Opcode.RETURN:
            return unwrap(result.update.return_value)
    return None


def _prepare_digits(value: str, total_digits: int, decimal_digits: int) -> list[int]:
    """Prepare digit list from string (what the frontend computes)."""
    clean = value.lstrip("+-")
    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        digit_str = left_adjust(clean.replace(".", ""), total_digits)
    return [int(ch) if ch.isdigit() else 0 for ch in digit_str]


class TestAlphanumericRedefines:
    """Write alphanumeric, read partial bytes as alphanumeric."""

    def test_write_date_read_year(self):
        """Write '20260301' (8 bytes), read first 4 bytes → '2026'."""
        vm = _make_vm()

        # Allocate 8-byte region
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        # Encode "20260301" as EBCDIC alphanumeric via IR
        enc_ir = build_encode_alphanumeric_ir("enc_date", length=8)
        vm.current_frame.registers["%p_value"] = "20260301"
        encoded = _execute_ir_sequence(vm, enc_ir)

        # Write encoded bytes to region at offset 0
        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%data"] = encoded
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%data"],
            ),
        )

        # Read first 4 bytes (REDEFINES as YEAR field)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%year_bytes",
                operands=["%rgn", "%off0", 4],
            ),
        )

        # Decode the 4 bytes as alphanumeric via IR
        dec_ir = build_decode_alphanumeric_ir("dec_year")
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers[
            "%year_bytes"
        ]
        year = _execute_ir_sequence(vm, dec_ir)

        assert year == "2026"

    def test_write_date_read_month(self):
        """Write '20260301', read bytes [4:6] → '03'."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        enc_ir = build_encode_alphanumeric_ir("enc_date", length=8)
        vm.current_frame.registers["%p_value"] = "20260301"
        encoded = _execute_ir_sequence(vm, enc_ir)

        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%data"] = encoded
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%data"],
            ),
        )

        # Read 2 bytes at offset 4 (month)
        vm.current_frame.registers["%off4"] = 4
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%month_bytes",
                operands=["%rgn", "%off4", 2],
            ),
        )

        dec_ir = build_decode_alphanumeric_ir("dec_month")
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers[
            "%month_bytes"
        ]
        month = _execute_ir_sequence(vm, dec_ir)

        assert month == "03"


class TestZonedDecimalRedefines:
    """Write zoned decimal, read same bytes as zoned decimal (overlay)."""

    def test_write_and_read_zoned(self):
        """Write zoned 12345 at offset 0, read it back."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[10],
            ),
        )

        # Encode zoned decimal 12345 (5 bytes, unsigned)
        digits = [1, 2, 3, 4, 5]
        enc_ir = build_encode_zoned_ir("enc_z", total_digits=5)
        vm.current_frame.registers["%p_digits"] = digits
        vm.current_frame.registers["%p_sign_nibble"] = 0x0F
        encoded = _execute_ir_sequence(vm, enc_ir)

        # Write to region at offset 0
        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%zdata"] = encoded
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 5, "%zdata"],
            ),
        )

        # Read back 5 bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%read_bytes",
                operands=["%rgn", "%off0", 5],
            ),
        )

        # Decode as zoned decimal
        dec_ir = build_decode_zoned_ir("dec_z", total_digits=5, decimal_digits=0)
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers[
            "%read_bytes"
        ]
        value = _execute_ir_sequence(vm, dec_ir)

        assert value == 12345.0


class TestMultiFieldRedefines:
    """Multiple fields sharing the same region at different offsets."""

    def test_two_fields_same_region(self):
        """Allocate 10-byte region, write zoned at [0:5], alphanumeric at [5:10]."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[10],
            ),
        )

        # Write zoned decimal 99999 at offset 0
        digits = [9, 9, 9, 9, 9]
        enc_z = build_encode_zoned_ir("enc_z", total_digits=5)
        vm.current_frame.registers["%p_digits"] = digits
        vm.current_frame.registers["%p_sign_nibble"] = 0x0F
        zoned_bytes = _execute_ir_sequence(vm, enc_z)

        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%zdata"] = zoned_bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 5, "%zdata"],
            ),
        )

        # Write alphanumeric "HELLO" at offset 5
        enc_a = build_encode_alphanumeric_ir("enc_a", length=5)
        vm.current_frame.registers["%p_value"] = "HELLO"
        alpha_bytes = _execute_ir_sequence(vm, enc_a)

        vm.current_frame.registers["%off5"] = 5
        vm.current_frame.registers["%adata"] = alpha_bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off5", 5, "%adata"],
            ),
        )

        # Read back zoned decimal from [0:5]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%z_read",
                operands=["%rgn", "%off0", 5],
            ),
        )
        dec_z = build_decode_zoned_ir("dec_z", total_digits=5, decimal_digits=0)
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers["%z_read"]
        z_value = _execute_ir_sequence(vm, dec_z)
        assert z_value == 99999.0

        # Read back alphanumeric from [5:10]
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%a_read",
                operands=["%rgn", "%off5", 5],
            ),
        )
        dec_a = build_decode_alphanumeric_ir("dec_a")
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers["%a_read"]
        a_value = _execute_ir_sequence(vm, dec_a)
        assert a_value == "HELLO"

    def test_overlapping_redefines(self):
        """Write alphanumeric at offset 0, read overlapping region as raw bytes."""
        vm = _make_vm()

        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%rgn",
                operands=[8],
            ),
        )

        # Write "ABCD1234" as alphanumeric
        enc_a = build_encode_alphanumeric_ir("enc_a", length=8)
        vm.current_frame.registers["%p_value"] = "ABCD1234"
        alpha_bytes = _execute_ir_sequence(vm, enc_a)

        vm.current_frame.registers["%off0"] = 0
        vm.current_frame.registers["%adata"] = alpha_bytes
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%rgn", "%off0", 8, "%adata"],
            ),
        )

        # Read bytes [4:8] — this is the REDEFINES overlay
        vm.current_frame.registers["%off4"] = 4
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%overlay",
                operands=["%rgn", "%off4", 4],
            ),
        )

        # Decode overlay as alphanumeric
        dec_a = build_decode_alphanumeric_ir("dec_a")
        vm.current_frame.registers["%p_data"] = vm.current_frame.registers["%overlay"]
        overlay_value = _execute_ir_sequence(vm, dec_a)

        assert overlay_value == "1234"
