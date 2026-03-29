"""Tests for IR encoder/decoder function builders.

Critical validation: IR-level encoding/decoding produces identical
results to the reference Python implementations when executed through the VM.
"""

from typing import Any

from interpreter.ir import Opcode
from interpreter.instructions import InstructionBase
from interpreter.types.typed_value import unwrap
from interpreter.vm.vm import VMState, apply_update
from interpreter.vm.vm_types import StackFrame
from interpreter.func_name import FuncName
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry

from interpreter.cobol.ir_encoders import (
    build_encode_zoned_ir,
    build_decode_zoned_ir,
    build_encode_zoned_separate_ir,
    build_decode_zoned_separate_ir,
    build_encode_comp3_ir,
    build_decode_comp3_ir,
    build_encode_alphanumeric_ir,
    build_encode_alphanumeric_justified_ir,
    build_decode_alphanumeric_ir,
    build_encode_binary_ir,
    build_decode_binary_ir,
    build_encode_float_ir,
    build_decode_float_ir,
)
from interpreter.cobol.zoned_decimal import encode_zoned, decode_zoned
from interpreter.cobol.comp3 import encode_comp3, decode_comp3
from interpreter.cobol.binary import encode_binary, decode_binary
from interpreter.cobol.float_encoding import (
    encode_comp1,
    decode_comp1,
    encode_comp2,
    decode_comp2,
)
from interpreter.cobol.alphanumeric import encode_alphanumeric, decode_alphanumeric
from interpreter.cobol.data_filters import align_decimal, left_adjust
from interpreter.register import Register


def _execute_ir(instructions: list[InstructionBase], registers: dict[str, Any]) -> Any:
    """Execute straight-line IR and return the RETURN value."""
    vm = VMState()
    vm.call_stack.append(
        StackFrame(function_name=FuncName("test"), registers=dict(registers))
    )
    ctx = _default_handler_context()

    for inst in instructions:
        if inst.opcode == Opcode.LABEL:
            continue
        result = LocalExecutor.execute(inst=inst, vm=vm, ctx=ctx)
        assert result.handled, f"Instruction not handled: {inst}"
        apply_update(vm, result.update)
        if inst.opcode == Opcode.RETURN:
            return unwrap(result.update.return_value)

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
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
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
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

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
        return _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

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
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

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


def _byte_count_for_digits(total_digits: int) -> int:
    """Determine byte count from total digit positions."""
    if total_digits <= 4:
        return 2
    if total_digits <= 9:
        return 4
    return 8


class TestEncodeBinaryIR:
    """Validate IR binary encoder against reference implementation."""

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
        byte_count = _byte_count_for_digits(total_digits)

        ir = build_encode_binary_ir(
            "enc_bin", total_digits=total_digits, byte_count=byte_count, signed=signed
        )
        return _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

    def test_unsigned_small(self):
        ir_result = self._run_encode("1234", 4, 0, signed=False)
        ref_result = encode_binary("1234", 4, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_signed_positive(self):
        ir_result = self._run_encode("1234", 4, 0, signed=True)
        ref_result = encode_binary("1234", 4, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_signed_negative(self):
        ir_result = self._run_encode("-1234", 4, 0, signed=True)
        ref_result = encode_binary("-1234", 4, 0, signed=True)
        assert bytes(ir_result) == ref_result

    def test_medium_integer(self):
        ir_result = self._run_encode("12345", 5, 0, signed=False)
        ref_result = encode_binary("12345", 5, 0, signed=False)
        assert bytes(ir_result) == ref_result

    def test_zero(self):
        ir_result = self._run_encode("0", 4, 0, signed=False)
        ref_result = encode_binary("0", 4, 0, signed=False)
        assert bytes(ir_result) == ref_result


class TestDecodeBinaryIR:
    """Validate IR binary decoder against reference implementation."""

    def _run_decode(
        self, data: bytes, byte_count: int, decimal_digits: int, signed: bool
    ) -> float:
        ir = build_decode_binary_ir(
            "dec_bin",
            byte_count=byte_count,
            decimal_digits=decimal_digits,
            signed=signed,
        )
        return _execute_ir(ir, {"%p_data": list(data)})

    def test_unsigned_small(self):
        data = (1234).to_bytes(2, "big", signed=False)
        assert self._run_decode(data, 2, 0, signed=False) == decode_binary(
            data, 0, signed=False
        )

    def test_signed_negative(self):
        data = (-1234).to_bytes(2, "big", signed=True)
        assert self._run_decode(data, 2, 0, signed=True) == decode_binary(
            data, 0, signed=True
        )

    def test_with_decimal(self):
        data = (12345).to_bytes(4, "big", signed=False)
        assert self._run_decode(data, 4, 2, signed=False) == decode_binary(
            data, 2, signed=False
        )


class TestBinaryRoundTripIR:
    """Encode via IR, decode via IR — full round trip."""

    def test_round_trip_unsigned(self):
        digits = [1, 2, 3, 4]
        sign_nib = 0x0F
        byte_count = 2

        enc_ir = build_encode_binary_ir(
            "enc", total_digits=4, byte_count=byte_count, signed=False
        )
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

        dec_ir = build_decode_binary_ir(
            "dec", byte_count=byte_count, decimal_digits=0, signed=False
        )
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == 1234.0

    def test_round_trip_signed_negative(self):
        digits = [0, 0, 4, 2]
        sign_nib = 0x0D
        byte_count = 2

        enc_ir = build_encode_binary_ir(
            "enc", total_digits=4, byte_count=byte_count, signed=True
        )
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

        dec_ir = build_decode_binary_ir(
            "dec", byte_count=byte_count, decimal_digits=0, signed=True
        )
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == -42.0


class TestEncodeFloatIR:
    """Validate IR float encoder against reference implementation."""

    def test_comp1_encode(self):
        ir = build_encode_float_ir("enc_f", byte_count=4)
        ir_result = _execute_ir(ir, {"%p_float_value": 3.14})
        ref_result = encode_comp1("3.14")
        assert bytes(ir_result) == ref_result

    def test_comp2_encode(self):
        ir = build_encode_float_ir("enc_f", byte_count=8)
        ir_result = _execute_ir(ir, {"%p_float_value": 3.14})
        ref_result = encode_comp2("3.14")
        assert bytes(ir_result) == ref_result

    def test_comp1_zero(self):
        ir = build_encode_float_ir("enc_f", byte_count=4)
        ir_result = _execute_ir(ir, {"%p_float_value": 0.0})
        ref_result = encode_comp1("0")
        assert bytes(ir_result) == ref_result

    def test_comp2_negative(self):
        ir = build_encode_float_ir("enc_f", byte_count=8)
        ir_result = _execute_ir(ir, {"%p_float_value": -100.5})
        ref_result = encode_comp2("-100.5")
        assert bytes(ir_result) == ref_result


class TestDecodeFloatIR:
    """Validate IR float decoder against reference implementation."""

    def test_comp1_decode(self):
        data = list(encode_comp1("3.14"))
        ir = build_decode_float_ir("dec_f", byte_count=4)
        ir_result = _execute_ir(ir, {"%p_data": data})
        assert abs(ir_result - decode_comp1(bytes(data))) < 1e-5

    def test_comp2_decode(self):
        data = list(encode_comp2("3.14"))
        ir = build_decode_float_ir("dec_f", byte_count=8)
        ir_result = _execute_ir(ir, {"%p_data": data})
        assert abs(ir_result - decode_comp2(bytes(data))) < 1e-10


class TestFloatRoundTripIR:
    """Encode via IR, decode via IR — full round trip for floats."""

    def test_comp1_round_trip(self):
        enc_ir = build_encode_float_ir("enc", byte_count=4)
        encoded = _execute_ir(enc_ir, {"%p_float_value": 42.0})

        dec_ir = build_decode_float_ir("dec", byte_count=4)
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert decoded == 42.0

    def test_comp2_round_trip(self):
        enc_ir = build_encode_float_ir("enc", byte_count=8)
        encoded = _execute_ir(enc_ir, {"%p_float_value": 3.14159265358979})

        dec_ir = build_decode_float_ir("dec", byte_count=8)
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})

        assert abs(decoded - 3.14159265358979) < 1e-10


class TestEncodeZonedLeadingIR:
    """Validate IR zoned encoder with SIGN IS LEADING (embedded)."""

    def test_leading_positive(self):
        digits = [1, 2, 3, 4, 5]
        sign_nib = 0x0C  # positive
        ir = build_encode_zoned_ir("enc_zl", total_digits=5, sign_leading=True)
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        # Byte 0: sign 0xC in high nibble, digit 1 in low → 0xC1
        assert result[0] == 0xC1
        # Remaining bytes: zone 0xF, digit in low
        assert result[1] == 0xF2
        assert result[4] == 0xF5

    def test_leading_negative(self):
        digits = [0, 0, 0, 4, 2]
        sign_nib = 0x0D  # negative
        ir = build_encode_zoned_ir("enc_zl", total_digits=5, sign_leading=True)
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        assert result[0] == 0xD0  # sign D, digit 0
        assert result[4] == 0xF2


class TestDecodeZonedLeadingIR:
    """Validate IR zoned decoder with SIGN IS LEADING (embedded)."""

    def test_leading_positive(self):
        # 0xC1 = sign C (positive), digit 1
        data = [0xC1, 0xF2, 0xF3, 0xF4, 0xF5]
        ir = build_decode_zoned_ir(
            "dec_zl", total_digits=5, decimal_digits=0, sign_leading=True
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 12345.0

    def test_leading_negative(self):
        data = [0xD1, 0xF2, 0xF3, 0xF4, 0xF5]
        ir = build_decode_zoned_ir(
            "dec_zl", total_digits=5, decimal_digits=0, sign_leading=True
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == -12345.0


class TestEncodeZonedSeparateIR:
    """Validate IR zoned encoder with SIGN SEPARATE CHARACTER."""

    def test_trailing_separate_positive(self):
        digits = [1, 2, 3]
        sign_nib = 0x0C  # positive
        ir = build_encode_zoned_separate_ir(
            "enc_zs", total_digits=3, sign_leading=False
        )
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        # 3 digit bytes + 1 sign byte
        assert len(result) == 4
        assert result[0] == 0xF1  # pure unsigned digit
        assert result[1] == 0xF2
        assert result[2] == 0xF3
        assert result[3] == 0x4E  # EBCDIC '+'

    def test_trailing_separate_negative(self):
        digits = [1, 2, 3]
        sign_nib = 0x0D  # negative
        ir = build_encode_zoned_separate_ir(
            "enc_zs", total_digits=3, sign_leading=False
        )
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        assert len(result) == 4
        assert result[3] == 0x60  # EBCDIC '-'

    def test_leading_separate_positive(self):
        digits = [4, 5]
        sign_nib = 0x0C
        ir = build_encode_zoned_separate_ir("enc_zs", total_digits=2, sign_leading=True)
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        assert len(result) == 3
        assert result[0] == 0x4E  # sign first
        assert result[1] == 0xF4
        assert result[2] == 0xF5

    def test_leading_separate_negative(self):
        digits = [4, 5]
        sign_nib = 0x0D
        ir = build_encode_zoned_separate_ir("enc_zs", total_digits=2, sign_leading=True)
        result = _execute_ir(
            ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )
        assert result[0] == 0x60  # '-' sign first


class TestDecodeZonedSeparateIR:
    """Validate IR zoned decoder with SIGN SEPARATE CHARACTER."""

    def test_trailing_separate_positive(self):
        # 3 digit bytes + '+' sign
        data = [0xF1, 0xF2, 0xF3, 0x4E]
        ir = build_decode_zoned_separate_ir(
            "dec_zs", total_digits=3, decimal_digits=0, sign_leading=False
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 123.0

    def test_trailing_separate_negative(self):
        data = [0xF1, 0xF2, 0xF3, 0x60]
        ir = build_decode_zoned_separate_ir(
            "dec_zs", total_digits=3, decimal_digits=0, sign_leading=False
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == -123.0

    def test_leading_separate_positive(self):
        data = [0x4E, 0xF4, 0xF5]
        ir = build_decode_zoned_separate_ir(
            "dec_zs", total_digits=2, decimal_digits=0, sign_leading=True
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 45.0

    def test_leading_separate_negative(self):
        data = [0x60, 0xF4, 0xF5]
        ir = build_decode_zoned_separate_ir(
            "dec_zs", total_digits=2, decimal_digits=0, sign_leading=True
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == -45.0

    def test_trailing_separate_with_decimal(self):
        data = [0xF1, 0xF2, 0xF3, 0xF4, 0x60]
        ir = build_decode_zoned_separate_ir(
            "dec_zs", total_digits=4, decimal_digits=2, sign_leading=False
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == -12.34


class TestZonedSeparateRoundTripIR:
    """Encode via IR, decode via IR — sign separate round trip."""

    def test_trailing_separate_round_trip(self):
        digits = [1, 2, 3, 4, 5]
        sign_nib = 0x0D  # negative

        enc_ir = build_encode_zoned_separate_ir(
            "enc", total_digits=5, sign_leading=False
        )
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

        dec_ir = build_decode_zoned_separate_ir(
            "dec", total_digits=5, decimal_digits=0, sign_leading=False
        )
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})
        assert decoded == -12345.0

    def test_leading_separate_round_trip(self):
        digits = [0, 4, 2]
        sign_nib = 0x0C  # positive

        enc_ir = build_encode_zoned_separate_ir(
            "enc", total_digits=3, sign_leading=True
        )
        encoded = _execute_ir(
            enc_ir, {"%p_digits": digits, Register("%p_sign_nibble"): sign_nib}
        )

        dec_ir = build_decode_zoned_separate_ir(
            "dec", total_digits=3, decimal_digits=0, sign_leading=True
        )
        decoded = _execute_ir(dec_ir, {"%p_data": encoded})
        assert decoded == 42.0


class TestEncodeAlphanumericJustifiedIR:
    """Validate IR right-justified alphanumeric encoder."""

    def test_short_value_left_padded(self):
        ir = build_encode_alphanumeric_justified_ir("enc_aj", length=8)
        ir_result = _execute_ir(ir, {"%p_value": "HI"})
        ref_left = encode_alphanumeric("HI", 8)
        # Right-justified: 6 spaces then HI
        # EBCDIC space = 0x40, H = 0xC8, I = 0xC9
        assert len(ir_result) == 8
        # First 6 should be EBCDIC spaces
        assert all(b == 0x40 for b in ir_result[:6])
        # Last 2 should be the EBCDIC of "HI"
        assert ir_result[6:] == list(encode_alphanumeric("HI", 2))

    def test_exact_length(self):
        ir = build_encode_alphanumeric_justified_ir("enc_aj", length=5)
        ir_result = _execute_ir(ir, {"%p_value": "HELLO"})
        ref_result = encode_alphanumeric("HELLO", 5)
        # Exact length: same as regular encoding
        assert bytes(ir_result) == ref_result

    def test_over_length_truncated_from_left(self):
        ir = build_encode_alphanumeric_justified_ir("enc_aj", length=3)
        ir_result = _execute_ir(ir, {"%p_value": "ABCDE"})
        # Right-justified: keep last 3 chars → "CDE"
        ref_cde = encode_alphanumeric("CDE", 3)
        assert bytes(ir_result) == ref_cde

    def test_empty_string_all_spaces(self):
        ir = build_encode_alphanumeric_justified_ir("enc_aj", length=4)
        ir_result = _execute_ir(ir, {"%p_value": ""})
        assert len(ir_result) == 4
        assert all(b == 0x40 for b in ir_result)
