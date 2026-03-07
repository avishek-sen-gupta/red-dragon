"""COMP-3 (packed BCD) encoding/decoding — reference implementation.

Ported from smojol's Comp3DataTypeSpec.java.
Two digits per byte, sign in the low nibble of the last byte.
Size = (total_digits // 2) + 1.
Sign nibble: 0xC = positive, 0xD = negative, 0xF = unsigned.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import ByteConstants
from interpreter.cobol.data_filters import align_decimal, left_adjust

logger = logging.getLogger(__name__)


def encode_comp3(
    value: str, total_digits: int, decimal_digits: int, signed: bool
) -> bytes:
    """Encode a numeric string as COMP-3 packed BCD bytes.

    Args:
        value: Numeric string, possibly with sign and decimal point.
        total_digits: Total number of digit positions.
        decimal_digits: Number of implied decimal positions.
        signed: Whether the field is signed.

    Returns:
        Byte sequence of length (total_digits // 2) + 1.
    """
    negative = value.startswith("-")
    clean = value.lstrip("+-")

    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        digit_str = left_adjust(clean.replace(".", ""), total_digits)

    # Determine sign nibble
    if not signed:
        sign_nibble = ByteConstants.SIGN_NIBBLE_UNSIGNED
    elif negative and any(ch != "0" for ch in digit_str):
        sign_nibble = ByteConstants.SIGN_NIBBLE_NEGATIVE
    else:
        sign_nibble = ByteConstants.SIGN_NIBBLE_POSITIVE

    byte_count = (total_digits // 2) + 1
    result = bytearray(byte_count)

    # Pack digits: two per byte, with the last byte holding the final
    # digit in the high nibble and the sign in the low nibble.
    # For odd total_digits, first byte has a leading zero in high nibble.
    # Pattern: digits are packed left-to-right, sign appended at the end.
    all_nibbles = [int(ch) if ch.isdigit() else 0 for ch in digit_str]
    # If total_digits is even, prepend a zero nibble so total nibbles
    # (digits + sign) fills byte_count bytes exactly.
    if total_digits % 2 == 0:
        all_nibbles = [0] + all_nibbles
    all_nibbles.append(sign_nibble)

    for i in range(byte_count):
        high = all_nibbles[i * 2]
        low = all_nibbles[i * 2 + 1]
        result[i] = (high << 4) | low

    logger.debug(
        "encode_comp3(%r, digits=%d, dec=%d, signed=%s) → %s",
        value,
        total_digits,
        decimal_digits,
        signed,
        result.hex(),
    )
    return bytes(result)


def decode_comp3(data: bytes, decimal_digits: int) -> float:
    """Decode COMP-3 packed BCD bytes to a float.

    Args:
        data: Packed BCD byte sequence.
        decimal_digits: Number of implied decimal positions.

    Returns:
        Decoded numeric value as float.
    """
    if not data:
        return 0.0

    # Extract all nibbles
    nibbles = []
    for b in data:
        nibbles.append((b >> 4) & ByteConstants.NIBBLE_MASK)
        nibbles.append(b & ByteConstants.NIBBLE_MASK)

    # Last nibble is sign
    sign_nibble = nibbles[-1]
    digit_nibbles = nibbles[:-1]

    negative = sign_nibble == ByteConstants.SIGN_NIBBLE_NEGATIVE

    int_value = sum(
        d * (10 ** (len(digit_nibbles) - 1 - i)) for i, d in enumerate(digit_nibbles)
    )

    result = (
        int_value / (10**decimal_digits) if decimal_digits > 0 else float(int_value)
    )

    if negative:
        result = -result

    logger.debug(
        "decode_comp3(%s, dec=%d) → %s",
        data.hex(),
        decimal_digits,
        result,
    )
    return result
