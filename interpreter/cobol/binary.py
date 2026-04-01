# pyright: standard
"""COMP/BINARY big-endian two's complement encoding/decoding — reference implementation.

COMP (also COMP-4, BINARY) stores numeric values as big-endian
two's complement integers. The PIC clause determines the digit count,
which determines byte size:
  - 1-4 digits  -> 2 bytes (halfword)
  - 5-9 digits  -> 4 bytes (fullword)
  - 10-18 digits -> 8 bytes (doubleword)

Decimal scaling is implicit (same as COMP-3): the stored integer
is the value multiplied by 10^decimal_digits.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging

from interpreter.cobol.data_filters import align_decimal, left_adjust

logger = logging.getLogger(__name__)

BINARY_BYTE_SIZES = {2: 4, 4: 9, 8: 18}


def _byte_count_for_digits(total_digits: int) -> int:
    """Determine byte count from total digit positions."""
    if total_digits <= 4:
        return 2
    if total_digits <= 9:
        return 4
    return 8


def encode_binary(
    value: str, total_digits: int, decimal_digits: int, signed: bool
) -> bytes:
    """Encode a numeric string as COMP/BINARY big-endian bytes.

    Args:
        value: Numeric string, possibly with sign and decimal point.
        total_digits: Total number of digit positions.
        decimal_digits: Number of implied decimal positions.
        signed: Whether the field is signed.

    Returns:
        Byte sequence of length determined by total_digits.
    """
    negative = value.startswith("-")
    clean = value.lstrip("+-")

    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        digit_str = left_adjust(clean.replace(".", ""), total_digits)

    int_value = int(digit_str) if digit_str else 0
    if negative and int_value != 0:
        int_value = -int_value

    byte_count = _byte_count_for_digits(total_digits)
    result = int_value.to_bytes(byte_count, "big", signed=signed)

    logger.debug(
        "encode_binary(%r, digits=%d, dec=%d, signed=%s) -> %s",
        value,
        total_digits,
        decimal_digits,
        signed,
        result.hex(),
    )
    return result


def decode_binary(data: bytes, decimal_digits: int, signed: bool) -> float:
    """Decode COMP/BINARY big-endian bytes to a float.

    Args:
        data: Big-endian byte sequence.
        decimal_digits: Number of implied decimal positions.
        signed: Whether the field is signed.

    Returns:
        Decoded numeric value as float.
    """
    if not data:
        return 0.0

    int_value = int.from_bytes(data, "big", signed=signed)

    result = (
        int_value / (10**decimal_digits) if decimal_digits > 0 else float(int_value)
    )

    logger.debug(
        "decode_binary(%s, dec=%d, signed=%s) -> %s",
        data.hex(),
        decimal_digits,
        signed,
        result,
    )
    return result
