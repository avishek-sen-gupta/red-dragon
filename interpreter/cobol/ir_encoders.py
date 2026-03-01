"""IR function builders for COBOL encoding/decoding.

Each builder generates a list of IRInstructions forming a straight-line
function body. The instructions use only primitive builtins from
byte_builtins.py and standard IR opcodes (arithmetic).

Generated IR is specialized for compile-time-known PIC parameters
(total_digits, decimal_digits, signed) — this matches how COBOL
compilers work, since field sizes are always known at compile time.

Function parameter conventions (received via pre-populated registers):
  - Encoders: %p_digits (list[int] of 0-9 values), %p_sign_nibble (int)
  - Decoders: %p_data (list[int] of byte values)
  - Alphanumeric encode: %p_value (str)
  - Alphanumeric decode: %p_data (list[int] of byte values)
"""

from __future__ import annotations

from interpreter.ir import IRInstruction, Opcode


class _RegCounter:
    """Generate unique register names for IR function bodies."""

    def __init__(self, prefix: str):
        self._prefix = prefix
        self._count = 0

    def next(self) -> str:
        name = f"%{self._prefix}_r{self._count}"
        self._count += 1
        return name


def build_encode_zoned_ir(func_name: str, total_digits: int) -> list[IRInstruction]:
    """Generate IR for zoned decimal encoding.

    Inputs: %p_digits (list[int]), %p_sign_nibble (int: 0xF/0xC/0xD)
    Output: list[int] of zoned decimal bytes (length = total_digits)
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Create result list filled with 0xF0 (zone nibble for unsigned digits)
    result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["__make_list", total_digits, 0xF0],
        )
    )

    # For each digit position, set the low nibble to the digit value
    for i in range(total_digits):
        digit = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=digit,
                operands=["__list_get", "%p_digits", i],
            )
        )

        byte_val = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=byte_val,
                operands=["__nibble_set", 0xF0, "low", digit],
            )
        )

        new_result = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=new_result,
                operands=["__list_set", result, i, byte_val],
            )
        )
        result = new_result

    # Set sign nibble on the last byte (high nibble)
    last_byte = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=last_byte,
            operands=["__list_get", result, total_digits - 1],
        )
    )

    signed_byte = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=signed_byte,
            operands=["__nibble_set", last_byte, "high", "%p_sign_nibble"],
        )
    )

    final_result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=final_result,
            operands=["__list_set", result, total_digits - 1, signed_byte],
        )
    )

    instructions.append(
        IRInstruction(
            opcode=Opcode.RETURN,
            operands=[final_result],
        )
    )

    return instructions


def build_decode_zoned_ir(
    func_name: str, total_digits: int, decimal_digits: int
) -> list[IRInstruction]:
    """Generate IR for zoned decimal decoding.

    Inputs: %p_data (list[int] of bytes)
    Output: float
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Accumulate digit values: value = sum(digit[i] * 10^(n-1-i))
    accum = rc.next()
    instructions.append(
        IRInstruction(opcode=Opcode.CONST, result_reg=accum, operands=[0])
    )

    for i in range(total_digits):
        byte_reg = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=byte_reg,
                operands=["__list_get", "%p_data", i],
            )
        )

        digit = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=digit,
                operands=["__nibble_get", byte_reg, "low"],
            )
        )

        power = 10 ** (total_digits - 1 - i)
        contribution = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=contribution,
                operands=["*", digit, power],
            )
        )

        new_accum = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=new_accum,
                operands=["+", accum, contribution],
            )
        )
        accum = new_accum

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=scaled,
                operands=["/", accum, divisor],
            )
        )
        accum = scaled
    else:
        # Convert to float for consistency
        as_float = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=as_float,
                operands=["float", accum],
            )
        )
        accum = as_float

    # Extract sign from last byte's high nibble
    last_byte = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=last_byte,
            operands=["__list_get", "%p_data", total_digits - 1],
        )
    )

    sign_nibble = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=sign_nibble,
            operands=["__nibble_get", last_byte, "high"],
        )
    )

    # is_negative = (sign_nibble == 0xD)
    is_neg = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=is_neg,
            operands=["==", sign_nibble, 0x0D],
        )
    )

    # sign_multiplier = 1 - 2 * is_negative
    two_neg = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=two_neg,
            operands=["*", 2, is_neg],
        )
    )

    sign_mult = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=sign_mult,
            operands=["-", 1, two_neg],
        )
    )

    final_result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=final_result,
            operands=["*", accum, sign_mult],
        )
    )

    instructions.append(
        IRInstruction(
            opcode=Opcode.RETURN,
            operands=[final_result],
        )
    )

    return instructions


def build_encode_comp3_ir(func_name: str, total_digits: int) -> list[IRInstruction]:
    """Generate IR for COMP-3 packed BCD encoding.

    Inputs: %p_digits (list[int]), %p_sign_nibble (int: 0xF/0xC/0xD)
    Output: list[int] of packed BCD bytes (length = total_digits // 2 + 1)
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []
    byte_count = (total_digits // 2) + 1

    # Build nibble list: for even total_digits, prepend a 0
    if total_digits % 2 == 0:
        zero_list = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=zero_list,
                operands=["__make_list", 1, 0],
            )
        )

        nibbles = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=nibbles,
                operands=["__list_concat", zero_list, "%p_digits"],
            )
        )
    else:
        nibbles = "%p_digits"

    # Append sign nibble: wrap it in a single-element list, then concat
    sign_list = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=sign_list,
            operands=["__make_list", 1, 0],
        )
    )

    sign_list_set = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=sign_list_set,
            operands=["__list_set", sign_list, 0, "%p_sign_nibble"],
        )
    )

    all_nibbles = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=all_nibbles,
            operands=["__list_concat", nibbles, sign_list_set],
        )
    )

    # Create result buffer
    result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["__make_list", byte_count, 0],
        )
    )

    # Pack nibble pairs into bytes (unrolled loop)
    for i in range(byte_count):
        high_nibble = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=high_nibble,
                operands=["__list_get", all_nibbles, i * 2],
            )
        )

        low_nibble = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=low_nibble,
                operands=["__list_get", all_nibbles, i * 2 + 1],
            )
        )

        byte_with_high = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=byte_with_high,
                operands=["__nibble_set", 0, "high", high_nibble],
            )
        )

        byte_complete = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=byte_complete,
                operands=["__nibble_set", byte_with_high, "low", low_nibble],
            )
        )

        new_result = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=new_result,
                operands=["__list_set", result, i, byte_complete],
            )
        )
        result = new_result

    instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=[result]))

    return instructions


def build_decode_comp3_ir(
    func_name: str, total_digits: int, decimal_digits: int
) -> list[IRInstruction]:
    """Generate IR for COMP-3 packed BCD decoding.

    Inputs: %p_data (list[int] of bytes)
    Output: float
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []
    byte_count = (total_digits // 2) + 1

    # Extract all nibbles from all bytes
    nibble_regs: list[str] = []
    for i in range(byte_count):
        byte_reg = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=byte_reg,
                operands=["__list_get", "%p_data", i],
            )
        )

        high = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=high,
                operands=["__nibble_get", byte_reg, "high"],
            )
        )
        nibble_regs.append(high)

        low = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=low,
                operands=["__nibble_get", byte_reg, "low"],
            )
        )
        nibble_regs.append(low)

    # Last nibble is sign, all others are digits
    sign_reg = nibble_regs[-1]
    digit_regs = nibble_regs[:-1]

    # Accumulate digits into a value
    accum = rc.next()
    instructions.append(
        IRInstruction(opcode=Opcode.CONST, result_reg=accum, operands=[0])
    )

    for i, dreg in enumerate(digit_regs):
        power = 10 ** (len(digit_regs) - 1 - i)
        contribution = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=contribution,
                operands=["*", dreg, power],
            )
        )

        new_accum = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=new_accum,
                operands=["+", accum, contribution],
            )
        )
        accum = new_accum

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=scaled,
                operands=["/", accum, divisor],
            )
        )
        accum = scaled
    else:
        as_float = rc.next()
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg=as_float,
                operands=["float", accum],
            )
        )
        accum = as_float

    # Apply sign: sign_nibble == 0xD → negative
    is_neg = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=is_neg,
            operands=["==", sign_reg, 0x0D],
        )
    )

    two_neg = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=two_neg,
            operands=["*", 2, is_neg],
        )
    )

    sign_mult = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=sign_mult,
            operands=["-", 1, two_neg],
        )
    )

    final_result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.BINOP,
            result_reg=final_result,
            operands=["*", accum, sign_mult],
        )
    )

    instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=[final_result]))

    return instructions


def build_encode_alphanumeric_ir(func_name: str, length: int) -> list[IRInstruction]:
    """Generate IR for alphanumeric EBCDIC encoding.

    Inputs: %p_value (str)
    Output: list[int] of EBCDIC bytes (length = `length`)
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Convert string to EBCDIC bytes
    ebcdic_bytes = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=ebcdic_bytes,
            operands=["__string_to_bytes", "%p_value", "ebcdic"],
        )
    )

    # Create padding (EBCDIC spaces = 0x40)
    padding = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=padding,
            operands=["__make_list", length, 0x40],
        )
    )

    # Concatenate input + padding, then slice to exact length
    # This handles both truncation (input too long) and padding (input too short)
    combined = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=combined,
            operands=["__list_concat", ebcdic_bytes, padding],
        )
    )

    result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["__list_slice", combined, 0, length],
        )
    )

    instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=[result]))

    return instructions


def build_decode_alphanumeric_ir(func_name: str) -> list[IRInstruction]:
    """Generate IR for alphanumeric EBCDIC decoding.

    Inputs: %p_data (list[int] of EBCDIC bytes)
    Output: str
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["__bytes_to_string", "%p_data", "ebcdic"],
        )
    )

    instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=[result]))

    return instructions
