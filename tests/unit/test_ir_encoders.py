"""Tests for IR encoder/decoder function builders.

Critical validation: IR-level encoding/decoding produces identical
results to the reference Python implementations when executed through the VM.
"""

from typing import Any

from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import StackFrame
from interpreter.executor import LocalExecutor
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry

from interpreter.cobol.ir_encoders import (
    build_encode_zoned_ir,
    build_decode_zoned_ir,
    build_encode_comp3_ir,
    build_decode_comp3_ir,
    build_encode_alphanumeric_ir,
    build_decode_alphanumeric_ir,
)
from interpreter.cobol.zoned_decimal import encode_zoned, decode_zoned
from interpreter.cobol.comp3 import encode_comp3, decode_comp3
from interpreter.cobol.alphanumeric import encode_alphanumeric, decode_alphanumeric
from interpreter.cobol.data_filters import align_decimal, left_adjust


def _execute_ir(instructions: list[IRInstruction], registers: dict[str, Any]) -> Any:
    """Execute straight-line IR and return the RETURN value."""
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test", registers=dict(registers)))
    cfg = CFG()
    registry = FunctionRegistry()

    for inst in instructions:
        if inst.opcode == Opcode.LABEL:
            continue
        result = LocalExecutor.execute(inst=inst, vm=vm, cfg=cfg, registry=registry)
        assert result.handled, f"Instruction not handled: {inst}"
        apply_update(vm, result.update)
        if inst.opcode == Opcode.RETURN:
            return result.update.return_value

    return None


def _prepare_zoned_digits(
    value: str, total_digits: int, decimal_digits: int
) -> tuple[list[int], int]:
    """Prepare digit list and sign nibble from a value string.

    This replicates what the COBOL frontend would compute.
    Returns (digit_list, sign_nibble).
    """
    negative = value.startswith("-")
    clean = value.lstrip("+-")

    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        digit_str = left_adjust(clean.replace(".", ""), total_digits)

    digits = [int(ch) if ch.isdigit() else 0 for ch in digit_str]
    return digits, negative


def _sign_nibble(signed: bool, negative: bool, has_nonzero: bool) -> int:
    """Compute the sign nibble value."""
    if not signed:
        return 0x0F
    if negative and has_nonzero:
        return 0x0D
    return 0x0C


class TestEncodeZonedIR:
    """Validate IR zoned decimal encoder against reference implementation."""

    def _run_encode(
        self,
        value: str,
        total_digits: int,
        decimal_digits: int,
        signed: bool,
    ) -> list[int]:
        digits, negative = _prepare_zoned_digits(value, total_digits, decimal_digits)
        has_nonzero = any(d != 0 for d in digits)
        sign_nib = _sign_nibble(signed, negative, has_nonzero)

        ir = build_encode_zoned_ir("enc_z", total_digits=total_digits)
        result = _execute_ir(ir, {"%p_digits": digits, "%p_sign_nibble": sign_nib})
        return result

    def test_unsigned_integer(self):
        ir_result = self._run_encode("12345", 5, 0, signed=False)
        ref_result = encode_zoned("12345", 5, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_signed_positive(self):
        ir_result = self._run_encode("12345", 5, 0, signed=True)
        ref_result = encode_zoned("12345", 5, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_signed_negative(self):
        ir_result = self._run_encode("-12345", 5, 0, signed=True)
        ref_result = encode_zoned("-12345", 5, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_with_decimal(self):
        ir_result = self._run_encode("2.3", 4, 2, signed=False)
        ref_result = encode_zoned("2.3", 4, 2, signed=False)
        assert bytes(ir_result) == ref_result

    def test_empty_string(self):
        ir_result = self._run_encode("", 3, 0, signed=False)
        ref_result = encode_zoned("", 3, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_negative_zero(self):
        ir_result = self._run_encode("-0", 3, 0, signed=True)
        ref_result = encode_zoned("-0", 3, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_single_digit(self):
        ir_result = self._run_encode("7", 1, 0, signed=False)
        ref_result = encode_zoned("7", 1, 0, signed=False)
        assert bytes(ir_result) == ref_result


class TestDecodeZonedIR:
    """Validate IR zoned decimal decoder against reference implementation."""

    def _run_decode(self, data: bytes, total_digits: int, decimal_digits: int) -> float:
        ir = build_decode_zoned_ir(
            "dec_z", total_digits=total_digits, decimal_digits=decimal_digits
        )
        result = _execute_ir(ir, {"%p_data": list(data)})
        return result

    def test_unsigned_integer(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])
        assert self._run_decode(data, 5, 0) == decode_zoned(data, 0)

    def test_with_decimal(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5])
        assert self._run_decode(data, 5, 2) == decode_zoned(data, 2)

    def test_signed_negative(self):
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xD5])
        assert self._run_decode(data, 5, 0) == decode_zoned(data, 0)

    def test_all_zeros(self):
        data = bytes([0xF0, 0xF0, 0xF0])
        assert self._run_decode(data, 3, 0) == decode_zoned(data, 0)


class TestZonedRoundTripIR:
    """Encode via IR, decode via IR — full round trip."""

    def test_round_trip(self):
        digits = [1, 2, 3, 4, 5]
        sign_nib = 0x0F

        enc_ir = build_encode_zoned_ir("enc", total_digits=5)
        encoded = _execute_ir(enc_ir, {"%p_digits": digits, "%p_sign_nibble": sign_nib})

        dec_ir = build_decode_zoned_ir("dec", total_digits=5, decimal_digits=0)
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == 12345.0


class TestEncodeComp3IR:
    """Validate IR COMP-3 encoder against reference implementation."""

    def _run_encode(
        self,
        value: str,
        total_digits: int,
        decimal_digits: int,
        signed: bool,
    ) -> list[int]:
        digits, negative = _prepare_zoned_digits(value, total_digits, decimal_digits)
        has_nonzero = any(d != 0 for d in digits)
        sign_nib = _sign_nibble(signed, negative, has_nonzero)

        ir = build_encode_comp3_ir("enc_c3", total_digits=total_digits)
        return _execute_ir(ir, {"%p_digits": digits, "%p_sign_nibble": sign_nib})

    def test_unsigned_integer(self):
        ir_result = self._run_encode("12345", 5, 0, signed=False)
        ref_result = encode_comp3("12345", 5, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_signed_positive(self):
        ir_result = self._run_encode("12345", 5, 0, signed=True)
        ref_result = encode_comp3("12345", 5, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_signed_negative(self):
        ir_result = self._run_encode("-12345", 5, 0, signed=True)
        ref_result = encode_comp3("-12345", 5, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_even_digits(self):
        ir_result = self._run_encode("1234", 4, 0, signed=False)
        ref_result = encode_comp3("1234", 4, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_zero(self):
        ir_result = self._run_encode("0", 3, 0, signed=False)
        ref_result = encode_comp3("0", 3, 0, signed=False)
        assert bytes(ir_result) == ref_result


class TestDecodeComp3IR:
    """Validate IR COMP-3 decoder against reference implementation."""

    def _run_decode(self, data: bytes, total_digits: int, decimal_digits: int) -> float:
        ir = build_decode_comp3_ir(
            "dec_c3",
            total_digits=total_digits,
            decimal_digits=decimal_digits,
        )
        return _execute_ir(ir, {"%p_data": list(data)})

    def test_unsigned_integer(self):
        data = bytes([0x12, 0x34, 0x5F])
        assert self._run_decode(data, 5, 0) == decode_comp3(data, 0)

    def test_signed_negative(self):
        data = bytes([0x12, 0x34, 0x5D])
        assert self._run_decode(data, 5, 0) == decode_comp3(data, 0)

    def test_with_decimal(self):
        data = bytes([0x12, 0x34, 0x5F])
        assert self._run_decode(data, 5, 2) == decode_comp3(data, 2)


class TestComp3RoundTripIR:
    def test_round_trip(self):
        digits = [1, 2, 3, 4, 5]
        sign_nib = 0x0F

        enc_ir = build_encode_comp3_ir("enc", total_digits=5)
        encoded = _execute_ir(enc_ir, {"%p_digits": digits, "%p_sign_nibble": sign_nib})

        dec_ir = build_decode_comp3_ir("dec", total_digits=5, decimal_digits=0)
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == 12345.0


class TestEncodeAlphanumericIR:
    """Validate IR alphanumeric encoder against reference implementation."""

    def test_exact_length(self):
        ir = build_encode_alphanumeric_ir("enc_a", length=5)
        ir_result = _execute_ir(ir, {"%p_value": "HELLO"})
        ref_result = encode_alphanumeric("HELLO", 5)
        assert bytes(ir_result) == ref_result

    def test_over_length_truncated(self):
        ir = build_encode_alphanumeric_ir("enc_a", length=5)
        ir_result = _execute_ir(ir, {"%p_value": "HELLO WORLD"})
        ref_result = encode_alphanumeric("HELLO WORLD", 5)
        assert bytes(ir_result) == ref_result

    def test_under_length_padded(self):
        ir = build_encode_alphanumeric_ir("enc_a", length=5)
        ir_result = _execute_ir(ir, {"%p_value": "HI"})
        ref_result = encode_alphanumeric("HI", 5)
        assert bytes(ir_result) == ref_result

    def test_empty_string(self):
        ir = build_encode_alphanumeric_ir("enc_a", length=3)
        ir_result = _execute_ir(ir, {"%p_value": ""})
        ref_result = encode_alphanumeric("", 3)
        assert bytes(ir_result) == ref_result


class TestDecodeAlphanumericIR:
    def test_decode_hello(self):
        data = list(encode_alphanumeric("HELLO", 5))
        ir = build_decode_alphanumeric_ir("dec_a")
        ir_result = _execute_ir(ir, {"%p_data": data})
        ref_result = decode_alphanumeric(bytes(data))
        assert ir_result == ref_result

    def test_decode_with_padding(self):
        data = list(encode_alphanumeric("HI", 5))
        ir = build_decode_alphanumeric_ir("dec_a")
        ir_result = _execute_ir(ir, {"%p_data": data})
        ref_result = decode_alphanumeric(bytes(data))
        assert ir_result == ref_result

    def test_decode_digits(self):
        data = list(encode_alphanumeric("20260301", 8))
        ir = build_decode_alphanumeric_ir("dec_a")
        ir_result = _execute_ir(ir, {"%p_data": data})
        assert ir_result == "20260301"


class TestAlphanumericRoundTripIR:
    def test_round_trip(self):
        enc_ir = build_encode_alphanumeric_ir("enc", length=8)
        encoded = _execute_ir(enc_ir, {"%p_value": "20260301"})

        dec_ir = build_decode_alphanumeric_ir("dec")
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == "20260301"
