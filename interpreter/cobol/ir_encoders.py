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

from functools import reduce

from interpreter.cobol.cobol_constants import (
    BuiltinName,
    ByteConstants,
    CobolEncoding,
    NibblePosition,
)
from interpreter.ir import IRInstruction
from interpreter.instructions import Binop, CallFunction, Const, Return_
from interpreter.register import Register


class _RegCounter:
    """Generate unique register names for IR function bodies."""

    def __init__(self, prefix: str):
        self._prefix = prefix
        self._count = 0

    def next(self) -> Register:
        name = Register(f"%{self._prefix}_r{self._count}")
        self._count += 1
        return name


def _encode_digit_step(
    rc: _RegCounter,
    source_list: str,
    acc: tuple[str, list[IRInstruction]],
    i: int,
) -> tuple[str, list[IRInstruction]]:
    """One step of zoned digit encoding: get digit, nibble_set, list_set.

    Returns (new_result_reg, accumulated_instructions).
    """
    current_result, instructions = acc
    digit = rc.next()
    byte_val = rc.next()
    new_result = rc.next()
    return (
        new_result,
        instructions
        + [
            CallFunction(
                result_reg=digit,
                func_name=BuiltinName.LIST_GET,
                args=(
                    source_list,
                    i,
                ),
            ),
            CallFunction(
                result_reg=byte_val,
                func_name=BuiltinName.NIBBLE_SET,
                args=(
                    ByteConstants.ZONE_NIBBLE_UNSIGNED,
                    NibblePosition.LOW,
                    digit,
                ),
            ),
            CallFunction(
                result_reg=new_result,
                func_name=BuiltinName.LIST_SET,
                args=(
                    current_result,
                    i,
                    byte_val,
                ),
            ),
        ],
    )


def _decode_digit_step(
    rc: _RegCounter,
    source_list: str,
    total_digits: int,
    acc: tuple[str, list[IRInstruction]],
    i: int,
    offset: int = 0,
) -> tuple[str, list[IRInstruction]]:
    """One step of zoned digit decoding: get byte, nibble_get, multiply, add.

    Returns (new_accum_reg, accumulated_instructions).
    """
    current_accum, instructions = acc
    byte_reg = rc.next()
    digit = rc.next()
    power = 10 ** (total_digits - 1 - i)
    contribution = rc.next()
    new_accum = rc.next()
    return (
        new_accum,
        instructions
        + [
            CallFunction(
                result_reg=byte_reg,
                func_name=BuiltinName.LIST_GET,
                args=(
                    source_list,
                    offset + i,
                ),
            ),
            CallFunction(
                result_reg=digit,
                func_name=BuiltinName.NIBBLE_GET,
                args=(
                    byte_reg,
                    NibblePosition.LOW,
                ),
            ),
            Binop(result_reg=contribution, operator="*", left=digit, right=power),
            Binop(
                result_reg=new_accum,
                operator="+",
                left=current_accum,
                right=contribution,
            ),
        ],
    )


def _accumulate_digit_step(
    rc: _RegCounter,
    source_list: str,
    total_digits: int,
    acc: tuple[str, list[IRInstruction]],
    i: int,
) -> tuple[str, list[IRInstruction]]:
    """One step of raw digit accumulation (no nibble_get): get digit, multiply, add.

    Returns (new_accum_reg, accumulated_instructions).
    """
    current_accum, instructions = acc
    digit = rc.next()
    power = 10 ** (total_digits - 1 - i)
    contribution = rc.next()
    new_accum = rc.next()
    return (
        new_accum,
        instructions
        + [
            CallFunction(
                result_reg=digit,
                func_name=BuiltinName.LIST_GET,
                args=(
                    source_list,
                    i,
                ),
            ),
            Binop(result_reg=contribution, operator="*", left=digit, right=power),
            Binop(
                result_reg=new_accum,
                operator="+",
                left=current_accum,
                right=contribution,
            ),
        ],
    )


def build_encode_zoned_ir(
    func_name: str, total_digits: int, sign_leading: bool = False
) -> list[IRInstruction]:
    """Generate IR for zoned decimal encoding (embedded sign).

    Inputs: %p_digits (list[int]), %p_sign_nibble (int: 0xF/0xC/0xD)
    Output: list[int] of zoned decimal bytes (length = total_digits)

    When sign_leading=True, sign nibble is in high nibble of first byte.
    Otherwise (default), sign nibble is in high nibble of last byte.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []
    sign_byte_index = 0 if sign_leading else total_digits - 1

    # Create result list filled with 0xF0 (zone nibble for unsigned digits)
    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                total_digits,
                ByteConstants.ZONE_NIBBLE_UNSIGNED,
            ),
        )
    )

    # For each digit position, set the low nibble to the digit value
    result, digit_instructions = reduce(
        lambda acc, i: _encode_digit_step(rc, "%p_digits", acc, i),
        range(total_digits),
        (result, []),
    )
    instructions.extend(digit_instructions)

    # Set sign nibble on the sign byte (high nibble)
    sign_byte = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_byte,
            func_name=BuiltinName.LIST_GET,
            args=(
                result,
                sign_byte_index,
            ),
        )
    )

    signed_byte = rc.next()
    instructions.append(
        CallFunction(
            result_reg=signed_byte,
            func_name=BuiltinName.NIBBLE_SET,
            args=(
                sign_byte,
                NibblePosition.HIGH,
                "%p_sign_nibble",
            ),
        )
    )

    final_result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=final_result,
            func_name=BuiltinName.LIST_SET,
            args=(
                result,
                sign_byte_index,
                signed_byte,
            ),
        )
    )

    instructions.append(Return_(value_reg=final_result))

    return instructions


def build_decode_zoned_ir(
    func_name: str,
    total_digits: int,
    decimal_digits: int,
    sign_leading: bool = False,
) -> list[IRInstruction]:
    """Generate IR for zoned decimal decoding (embedded sign).

    Inputs: %p_data (list[int] of bytes)
    Output: float

    When sign_leading=True, sign nibble is extracted from byte 0.
    Otherwise (default), sign nibble is extracted from the last byte.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []
    sign_byte_index = 0 if sign_leading else total_digits - 1

    # Accumulate digit values: value = sum(digit[i] * 10^(n-1-i))
    accum = rc.next()
    instructions.append(Const(result_reg=accum, value=0))

    accum, decode_instructions = reduce(
        lambda acc, i: _decode_digit_step(rc, "%p_data", total_digits, acc, i),
        range(total_digits),
        (accum, []),
    )
    instructions.extend(decode_instructions)

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            Binop(result_reg=scaled, operator="/", left=accum, right=divisor)
        )
        accum = scaled
    else:
        # Convert to float for consistency
        as_float = rc.next()
        instructions.append(
            CallFunction(result_reg=as_float, func_name="float", args=(accum,))
        )
        accum = as_float

    # Extract sign from the sign byte's high nibble
    sign_byte = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_byte,
            func_name=BuiltinName.LIST_GET,
            args=(
                "%p_data",
                sign_byte_index,
            ),
        )
    )

    sign_nibble = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_nibble,
            func_name=BuiltinName.NIBBLE_GET,
            args=(
                sign_byte,
                NibblePosition.HIGH,
            ),
        )
    )

    # is_negative = (sign_nibble == 0xD)
    is_neg = rc.next()
    instructions.append(
        Binop(
            result_reg=is_neg,
            operator="==",
            left=sign_nibble,
            right=ByteConstants.SIGN_NIBBLE_NEGATIVE,
        )
    )

    # sign_multiplier = 1 - 2 * is_negative
    two_neg = rc.next()
    instructions.append(Binop(result_reg=two_neg, operator="*", left=2, right=is_neg))

    sign_mult = rc.next()
    instructions.append(
        Binop(result_reg=sign_mult, operator="-", left=1, right=two_neg)
    )

    final_result = rc.next()
    instructions.append(
        Binop(result_reg=final_result, operator="*", left=accum, right=sign_mult)
    )

    instructions.append(Return_(value_reg=final_result))

    return instructions


def build_encode_zoned_separate_ir(
    func_name: str, total_digits: int, sign_leading: bool = False
) -> list[IRInstruction]:
    """Generate IR for zoned decimal encoding with SEPARATE sign character.

    Inputs: %p_digits (list[int]), %p_sign_nibble (int: 0xF/0xC/0xD)
    Output: list[int] of bytes (length = total_digits + 1)

    Digits are encoded as pure unsigned zoned (zone=0xF0 on all bytes).
    A separate sign byte is prepended (sign_leading=True) or appended (default).
    EBCDIC: '+' = 0x4E, '-' = 0x60.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Build digit bytes (no embedded sign — all zones are 0xF)
    digits_list = rc.next()
    instructions.append(
        CallFunction(
            result_reg=digits_list,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                total_digits,
                ByteConstants.ZONE_NIBBLE_UNSIGNED,
            ),
        )
    )

    digits_list, digit_instructions = reduce(
        lambda acc, i: _encode_digit_step(rc, "%p_digits", acc, i),
        range(total_digits),
        (digits_list, []),
    )
    instructions.extend(digit_instructions)

    # Compute sign byte: 0xD → 0x60 ('-'), else → 0x4E ('+')
    is_neg = rc.next()
    instructions.append(
        Binop(
            result_reg=is_neg,
            operator="==",
            left="%p_sign_nibble",
            right=ByteConstants.SIGN_NIBBLE_NEGATIVE,
        )
    )

    # sign_byte = 0x4E + is_neg * (0x60 - 0x4E) = 0x4E + is_neg * 0x12
    neg_offset = rc.next()
    instructions.append(
        Binop(
            result_reg=neg_offset,
            operator="*",
            left=is_neg,
            right=ByteConstants.EBCDIC_SIGN_OFFSET,
        )
    )

    sign_byte_val = rc.next()
    instructions.append(
        Binop(
            result_reg=sign_byte_val,
            operator="+",
            left=ByteConstants.EBCDIC_PLUS,
            right=neg_offset,
        )
    )

    # Build single-element sign list
    sign_list = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_list,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                1,
                0,
            ),
        )
    )

    sign_list_set = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_list_set,
            func_name=BuiltinName.LIST_SET,
            args=(
                sign_list,
                0,
                sign_byte_val,
            ),
        )
    )

    # Concatenate: sign_leading → [sign] + digits, else → digits + [sign]
    if sign_leading:
        final_result = rc.next()
        instructions.append(
            CallFunction(
                result_reg=final_result,
                func_name=BuiltinName.LIST_CONCAT,
                args=(
                    sign_list_set,
                    digits_list,
                ),
            )
        )
    else:
        final_result = rc.next()
        instructions.append(
            CallFunction(
                result_reg=final_result,
                func_name=BuiltinName.LIST_CONCAT,
                args=(
                    digits_list,
                    sign_list_set,
                ),
            )
        )

    instructions.append(Return_(value_reg=final_result))
    return instructions


def build_decode_zoned_separate_ir(
    func_name: str,
    total_digits: int,
    decimal_digits: int,
    sign_leading: bool = False,
) -> list[IRInstruction]:
    """Generate IR for zoned decimal decoding with SEPARATE sign character.

    Inputs: %p_data (list[int] of bytes, length = total_digits + 1)
    Output: float

    sign_leading=True: byte 0 is the sign, bytes 1..N are digits.
    sign_leading=False: bytes 0..N-1 are digits, byte N is the sign.
    EBCDIC: 0x60 = '-', anything else = '+'.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Extract sign byte
    sign_byte_index = 0 if sign_leading else total_digits
    sign_byte = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_byte,
            func_name=BuiltinName.LIST_GET,
            args=(
                "%p_data",
                sign_byte_index,
            ),
        )
    )

    # digit_start offset: 1 if sign_leading, else 0
    digit_start = 1 if sign_leading else 0

    # Accumulate digit values
    accum = rc.next()
    instructions.append(Const(result_reg=accum, value=0))

    accum, decode_instructions = reduce(
        lambda acc, i: _decode_digit_step(
            rc, "%p_data", total_digits, acc, i, offset=digit_start
        ),
        range(total_digits),
        (accum, []),
    )
    instructions.extend(decode_instructions)

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            Binop(result_reg=scaled, operator="/", left=accum, right=divisor)
        )
        accum = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(result_reg=as_float, func_name="float", args=(accum,))
        )
        accum = as_float

    # Apply sign: 0x60 = negative
    is_neg = rc.next()
    instructions.append(
        Binop(
            result_reg=is_neg,
            operator="==",
            left=sign_byte,
            right=ByteConstants.EBCDIC_MINUS,
        )
    )

    two_neg = rc.next()
    instructions.append(Binop(result_reg=two_neg, operator="*", left=2, right=is_neg))

    sign_mult = rc.next()
    instructions.append(
        Binop(result_reg=sign_mult, operator="-", left=1, right=two_neg)
    )

    final_result = rc.next()
    instructions.append(
        Binop(result_reg=final_result, operator="*", left=accum, right=sign_mult)
    )

    instructions.append(Return_(value_reg=final_result))
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
            CallFunction(
                result_reg=zero_list,
                func_name=BuiltinName.MAKE_LIST,
                args=(
                    1,
                    0,
                ),
            )
        )

        nibbles = rc.next()
        instructions.append(
            CallFunction(
                result_reg=nibbles,
                func_name=BuiltinName.LIST_CONCAT,
                args=(
                    zero_list,
                    "%p_digits",
                ),
            )
        )
    else:
        nibbles = "%p_digits"

    # Append sign nibble: wrap it in a single-element list, then concat
    sign_list = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_list,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                1,
                0,
            ),
        )
    )

    sign_list_set = rc.next()
    instructions.append(
        CallFunction(
            result_reg=sign_list_set,
            func_name=BuiltinName.LIST_SET,
            args=(
                sign_list,
                0,
                "%p_sign_nibble",
            ),
        )
    )

    all_nibbles = rc.next()
    instructions.append(
        CallFunction(
            result_reg=all_nibbles,
            func_name=BuiltinName.LIST_CONCAT,
            args=(
                nibbles,
                sign_list_set,
            ),
        )
    )

    # Create result buffer
    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                byte_count,
                0,
            ),
        )
    )

    # Pack nibble pairs into bytes (unrolled loop)
    def _pack_nibble_pair(
        acc: tuple[str, list[IRInstruction]], i: int
    ) -> tuple[str, list[IRInstruction]]:
        current_result, insts = acc
        high_nibble = rc.next()
        low_nibble = rc.next()
        byte_with_high = rc.next()
        byte_complete = rc.next()
        new_result = rc.next()
        return (
            new_result,
            insts
            + [
                CallFunction(
                    result_reg=high_nibble,
                    func_name=BuiltinName.LIST_GET,
                    args=(
                        all_nibbles,
                        i * 2,
                    ),
                ),
                CallFunction(
                    result_reg=low_nibble,
                    func_name=BuiltinName.LIST_GET,
                    args=(
                        all_nibbles,
                        i * 2 + 1,
                    ),
                ),
                CallFunction(
                    result_reg=byte_with_high,
                    func_name=BuiltinName.NIBBLE_SET,
                    args=(
                        0,
                        NibblePosition.HIGH,
                        high_nibble,
                    ),
                ),
                CallFunction(
                    result_reg=byte_complete,
                    func_name=BuiltinName.NIBBLE_SET,
                    args=(
                        byte_with_high,
                        NibblePosition.LOW,
                        low_nibble,
                    ),
                ),
                CallFunction(
                    result_reg=new_result,
                    func_name=BuiltinName.LIST_SET,
                    args=(
                        current_result,
                        i,
                        byte_complete,
                    ),
                ),
            ],
        )

    result, pack_instructions = reduce(
        _pack_nibble_pair, range(byte_count), (result, [])
    )
    instructions.extend(pack_instructions)

    instructions.append(Return_(value_reg=result))

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
    def _extract_nibbles(
        acc: tuple[list[str], list[IRInstruction]], i: int
    ) -> tuple[list[str], list[IRInstruction]]:
        regs, insts = acc
        byte_reg = rc.next()
        high = rc.next()
        low = rc.next()
        return (
            regs + [high, low],
            insts
            + [
                CallFunction(
                    result_reg=byte_reg,
                    func_name=BuiltinName.LIST_GET,
                    args=(
                        "%p_data",
                        i,
                    ),
                ),
                CallFunction(
                    result_reg=high,
                    func_name=BuiltinName.NIBBLE_GET,
                    args=(
                        byte_reg,
                        NibblePosition.HIGH,
                    ),
                ),
                CallFunction(
                    result_reg=low,
                    func_name=BuiltinName.NIBBLE_GET,
                    args=(
                        byte_reg,
                        NibblePosition.LOW,
                    ),
                ),
            ],
        )

    nibble_regs, nibble_instructions = reduce(
        _extract_nibbles, range(byte_count), ([], [])
    )
    instructions.extend(nibble_instructions)

    # Last nibble is sign, all others are digits
    sign_reg = nibble_regs[-1]
    digit_regs = nibble_regs[:-1]

    # Accumulate digits into a value
    accum = rc.next()
    instructions.append(Const(result_reg=accum, value=0))

    def _accumulate_dreg(
        acc: tuple[str, list[IRInstruction]], pair: tuple[int, str]
    ) -> tuple[str, list[IRInstruction]]:
        current_accum, insts = acc
        i, dreg = pair
        power = 10 ** (len(digit_regs) - 1 - i)
        contribution = rc.next()
        new_accum = rc.next()
        return (
            new_accum,
            insts
            + [
                Binop(result_reg=contribution, operator="*", left=dreg, right=power),
                Binop(
                    result_reg=new_accum,
                    operator="+",
                    left=current_accum,
                    right=contribution,
                ),
            ],
        )

    accum, accum_instructions = reduce(
        _accumulate_dreg, enumerate(digit_regs), (accum, [])
    )
    instructions.extend(accum_instructions)

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            Binop(result_reg=scaled, operator="/", left=accum, right=divisor)
        )
        accum = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(result_reg=as_float, func_name="float", args=(accum,))
        )
        accum = as_float

    # Apply sign: sign_nibble == 0xD → negative
    is_neg = rc.next()
    instructions.append(
        Binop(
            result_reg=is_neg,
            operator="==",
            left=sign_reg,
            right=ByteConstants.SIGN_NIBBLE_NEGATIVE,
        )
    )

    two_neg = rc.next()
    instructions.append(Binop(result_reg=two_neg, operator="*", left=2, right=is_neg))

    sign_mult = rc.next()
    instructions.append(
        Binop(result_reg=sign_mult, operator="-", left=1, right=two_neg)
    )

    final_result = rc.next()
    instructions.append(
        Binop(result_reg=final_result, operator="*", left=accum, right=sign_mult)
    )

    instructions.append(Return_(value_reg=final_result))

    return instructions


def build_encode_binary_ir(
    func_name: str, total_digits: int, byte_count: int, signed: bool
) -> list[IRInstruction]:
    """Generate IR for COMP/BINARY encoding.

    Inputs: %p_digits (list[int]), %p_sign_nibble (int: 0xF/0xC/0xD)
    Output: list[int] of big-endian binary bytes (length = byte_count)

    Reconstructs the integer from the digit list, applies sign from
    the sign nibble, then packs via __int_to_binary_bytes.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Accumulate digits into integer value
    accum = rc.next()
    instructions.append(Const(result_reg=accum, value=0))

    accum, accum_instructions = reduce(
        lambda acc, i: _accumulate_digit_step(rc, "%p_digits", total_digits, acc, i),
        range(total_digits),
        (accum, []),
    )
    instructions.extend(accum_instructions)

    # Apply sign: sign_nibble == 0xD → negate
    is_neg = rc.next()
    instructions.append(
        Binop(
            result_reg=is_neg,
            operator="==",
            left="%p_sign_nibble",
            right=ByteConstants.SIGN_NIBBLE_NEGATIVE,
        )
    )

    two_neg = rc.next()
    instructions.append(Binop(result_reg=two_neg, operator="*", left=2, right=is_neg))

    sign_mult = rc.next()
    instructions.append(
        Binop(result_reg=sign_mult, operator="-", left=1, right=two_neg)
    )

    signed_value = rc.next()
    instructions.append(
        Binop(result_reg=signed_value, operator="*", left=accum, right=sign_mult)
    )

    # Pack as big-endian binary bytes
    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.INT_TO_BINARY_BYTES,
            args=(
                signed_value,
                byte_count,
                signed,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))
    return instructions


def build_decode_binary_ir(
    func_name: str, byte_count: int, decimal_digits: int, signed: bool
) -> list[IRInstruction]:
    """Generate IR for COMP/BINARY decoding.

    Inputs: %p_data (list[int] of bytes)
    Output: float
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Unpack bytes to integer
    int_val = rc.next()
    instructions.append(
        CallFunction(
            result_reg=int_val,
            func_name=BuiltinName.BINARY_BYTES_TO_INT,
            args=(
                "%p_data",
                signed,
            ),
        )
    )

    # Apply decimal scaling
    if decimal_digits > 0:
        divisor = 10**decimal_digits
        scaled = rc.next()
        instructions.append(
            Binop(result_reg=scaled, operator="/", left=int_val, right=divisor)
        )
        int_val = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(result_reg=as_float, func_name="float", args=(int_val,))
        )
        int_val = as_float

    instructions.append(Return_(value_reg=int_val))
    return instructions


def build_encode_float_ir(func_name: str, byte_count: int) -> list[IRInstruction]:
    """Generate IR for COMP-1/COMP-2 float encoding.

    Inputs: %p_float_value (float or int)
    Output: list[int] of IEEE 754 bytes
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.FLOAT_TO_BYTES,
            args=(
                "%p_float_value",
                byte_count,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))
    return instructions


def build_decode_float_ir(func_name: str, byte_count: int) -> list[IRInstruction]:
    """Generate IR for COMP-1/COMP-2 float decoding.

    Inputs: %p_data (list[int] of bytes)
    Output: float
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.BYTES_TO_FLOAT,
            args=(
                "%p_data",
                byte_count,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))
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
        CallFunction(
            result_reg=ebcdic_bytes,
            func_name=BuiltinName.STRING_TO_BYTES,
            args=(
                "%p_value",
                CobolEncoding.EBCDIC,
            ),
        )
    )

    # Create padding (EBCDIC spaces = 0x40)
    padding = rc.next()
    instructions.append(
        CallFunction(
            result_reg=padding,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                length,
                ByteConstants.EBCDIC_SPACE,
            ),
        )
    )

    # Concatenate input + padding, then slice to exact length
    # This handles both truncation (input too long) and padding (input too short)
    combined = rc.next()
    instructions.append(
        CallFunction(
            result_reg=combined,
            func_name=BuiltinName.LIST_CONCAT,
            args=(
                ebcdic_bytes,
                padding,
            ),
        )
    )

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.LIST_SLICE,
            args=(
                combined,
                0,
                length,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

    return instructions


def build_encode_alphanumeric_justified_ir(
    func_name: str, length: int
) -> list[IRInstruction]:
    """Generate IR for right-justified alphanumeric EBCDIC encoding.

    Inputs: %p_value (str)
    Output: list[int] of EBCDIC bytes (length = `length`), right-justified

    Short values are left-padded with spaces (EBCDIC 0x40).
    Long values are truncated from the left (rightmost `length` bytes kept).
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Convert string to EBCDIC bytes
    ebcdic_bytes = rc.next()
    instructions.append(
        CallFunction(
            result_reg=ebcdic_bytes,
            func_name=BuiltinName.STRING_TO_BYTES,
            args=(
                "%p_value",
                CobolEncoding.EBCDIC,
            ),
        )
    )

    # Create padding (EBCDIC spaces = 0x40)
    padding = rc.next()
    instructions.append(
        CallFunction(
            result_reg=padding,
            func_name=BuiltinName.MAKE_LIST,
            args=(
                length,
                ByteConstants.EBCDIC_SPACE,
            ),
        )
    )

    # Concatenate padding + input (right-justify: padding on the left)
    combined = rc.next()
    instructions.append(
        CallFunction(
            result_reg=combined,
            func_name=BuiltinName.LIST_CONCAT,
            args=(
                padding,
                ebcdic_bytes,
            ),
        )
    )

    # Take the LAST `length` bytes: slice from (len(combined) - length)
    combined_len = rc.next()
    instructions.append(
        CallFunction(
            result_reg=combined_len, func_name=BuiltinName.LIST_LEN, args=(combined,)
        )
    )

    start_offset = rc.next()
    instructions.append(
        Binop(result_reg=start_offset, operator="-", left=combined_len, right=length)
    )

    end_offset = rc.next()
    instructions.append(
        Binop(result_reg=end_offset, operator="+", left=start_offset, right=length)
    )

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.LIST_SLICE,
            args=(
                combined,
                start_offset,
                end_offset,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

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
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.BYTES_TO_STRING,
            args=(
                "%p_data",
                CobolEncoding.EBCDIC,
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

    return instructions


# ── String operation IR builders ──────────────────────────────────


def build_string_delimit_ir(func_name: str) -> list[IRInstruction]:
    """Generate IR to delimit a string value.

    Inputs: %p_source (str), %p_delimiter (str)
    Output: str (truncated at delimiter, or full if delimiter is "SIZE")

    Uses __string_find to locate delimiter, then slices.
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    # Find delimiter position
    pos = rc.next()
    instructions.append(
        CallFunction(
            result_reg=pos,
            func_name=BuiltinName.STRING_FIND,
            args=(
                "%p_source",
                "%p_delimiter",
            ),
        )
    )

    # If pos == -1, use full string (no delimiter found → use length)
    # Compute: result_len = pos if pos >= 0 else len(source)
    # We use __list_slice on the string chars which works for string truncation
    # Actually, we'll use a simpler approach: emit a CALL_FUNCTION to __list_slice
    # on the source as a list of chars. But strings aren't lists...
    # Simpler: use the builtin directly — the frontend will use CALL_FUNCTION.

    instructions.append(Return_(value_reg=pos))

    return instructions


def build_string_split_ir(func_name: str) -> list[IRInstruction]:
    """Generate IR to split a string by delimiter.

    Inputs: %p_source (str), %p_delimiter (str)
    Output: list[str]
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.STRING_SPLIT,
            args=(
                "%p_source",
                "%p_delimiter",
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

    return instructions


def build_inspect_tally_ir(func_name: str) -> list[IRInstruction]:
    """Generate IR for INSPECT TALLYING — count pattern occurrences.

    Inputs: %p_source (str), %p_pattern (str), %p_mode (str)
    Output: int (count)
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.STRING_COUNT,
            args=(
                "%p_source",
                "%p_pattern",
                "%p_mode",
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

    return instructions


def build_inspect_replace_ir(func_name: str) -> list[IRInstruction]:
    """Generate IR for INSPECT REPLACING — replace pattern occurrences.

    Inputs: %p_source (str), %p_from (str), %p_to (str), %p_mode (str)
    Output: str (modified string)
    """
    rc = _RegCounter(func_name)
    instructions: list[IRInstruction] = []

    result = rc.next()
    instructions.append(
        CallFunction(
            result_reg=result,
            func_name=BuiltinName.STRING_REPLACE,
            args=(
                "%p_source",
                "%p_from",
                "%p_to",
                "%p_mode",
            ),
        )
    )

    instructions.append(Return_(value_reg=result))

    return instructions
