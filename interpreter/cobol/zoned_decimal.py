"""Zoned decimal encoding/decoding — reference implementation.

Ported from smojol's ZonedDecimalDataTypeSpec.java.
Each digit occupies one byte: zone nibble (high) + digit nibble (low).
Zone is 0xF for all bytes except the last, where it encodes sign:
  0xC = positive, 0xD = negative, 0xF = unsigned.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging

from interpreter.cobol.data_filters import align_decimal, left_adjust
from interpreter.cobol.ebcdic_table import EbcdicTable

logger = logging.getLogger(__name__)


def encode_zoned(
    value: str, total_digits: int, decimal_digits: int, signed: bool
) -> bytes:
    """Encode a numeric string as zoned decimal bytes.

    Args:
        value: Numeric string, possibly with sign and decimal point.
        total_digits: Total number of digit positions (PIC size).
        decimal_digits: Number of implied decimal positions (V digits).
        signed: Whether the field is signed (S in PIC).

    Returns:
        Byte sequence of length total_digits.
    """
    negative = value.startswith("-")
    clean = value.lstrip("+-")

    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        digit_str = left_adjust(clean.replace(".", ""), total_digits)

    result = bytearray(total_digits)
    for i, ch in enumerate(digit_str):
        digit = int(ch) if ch.isdigit() else 0
        zone = 0xF0
        result[i] = zone | digit

    # Set sign nibble on last byte
    if total_digits > 0:
        last_digit = result[-1] & 0x0F
        if not signed:
            result[-1] = 0xF0 | last_digit
        elif negative and any(b & 0x0F for b in result):
            # Only encode negative if value is non-zero
            result[-1] = 0xD0 | last_digit
        else:
            result[-1] = 0xC0 | last_digit

    logger.debug(
        "encode_zoned(%r, digits=%d, dec=%d, signed=%s) → %s",
        value,
        total_digits,
        decimal_digits,
        signed,
        result.hex(),
    )
    return bytes(result)


def decode_zoned(data: bytes, decimal_digits: int) -> float:
    """Decode zoned decimal bytes to a float.

    Args:
        data: Zoned decimal byte sequence.
        decimal_digits: Number of implied decimal positions.

    Returns:
        Decoded numeric value as float.
    """
    if not data:
        return 0.0

    digits = [b & 0x0F for b in data]
    sign_nibble = (data[-1] >> 4) & 0x0F
    negative = sign_nibble == 0x0D

    int_value = sum(d * (10 ** (len(digits) - 1 - i)) for i, d in enumerate(digits))

    result = (
        int_value / (10**decimal_digits) if decimal_digits > 0 else float(int_value)
    )

    if negative:
        result = -result

    logger.debug(
        "decode_zoned(%s, dec=%d) → %s",
        data.hex(),
        decimal_digits,
        result,
    )
    return result
