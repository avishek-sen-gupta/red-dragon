"""COMP-1 and COMP-2 IEEE 754 float encoding/decoding — reference implementation.

COMP-1: Single-precision IEEE 754 float, 4 bytes, big-endian.
COMP-2: Double-precision IEEE 754 float, 8 bytes, big-endian.

Neither type uses a PIC clause — they are always their fixed size.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging
import struct

logger = logging.getLogger(__name__)


def encode_comp1(value: str) -> bytes:
    """Encode a numeric string as COMP-1 (single-precision float).

    Args:
        value: Numeric string (e.g. "3.14", "-100.0", "0").

    Returns:
        4-byte big-endian IEEE 754 single-precision representation.
    """
    float_val = float(value)
    result = struct.pack(">f", float_val)

    logger.debug("encode_comp1(%r) -> %s", value, result.hex())
    return result


def decode_comp1(data: bytes) -> float:
    """Decode COMP-1 (single-precision float) bytes to a float.

    Args:
        data: 4-byte big-endian IEEE 754 representation.

    Returns:
        Decoded float value.
    """
    if not data:
        return 0.0

    (result,) = struct.unpack(">f", data)

    logger.debug("decode_comp1(%s) -> %s", data.hex(), result)
    return result


def encode_comp2(value: str) -> bytes:
    """Encode a numeric string as COMP-2 (double-precision float).

    Args:
        value: Numeric string (e.g. "3.14159265358979", "-100.0", "0").

    Returns:
        8-byte big-endian IEEE 754 double-precision representation.
    """
    float_val = float(value)
    result = struct.pack(">d", float_val)

    logger.debug("encode_comp2(%r) -> %s", value, result.hex())
    return result


def decode_comp2(data: bytes) -> float:
    """Decode COMP-2 (double-precision float) bytes to a float.

    Args:
        data: 8-byte big-endian IEEE 754 representation.

    Returns:
        Decoded float value.
    """
    if not data:
        return 0.0

    (result,) = struct.unpack(">d", data)

    logger.debug("decode_comp2(%s) -> %s", data.hex(), result)
    return result
