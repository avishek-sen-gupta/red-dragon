"""Alphanumeric encoding/decoding — reference implementation.

Ported from smojol's AlphanumericDataTypeSpec.java.
Uses EBCDIC encoding, right-pads with EBCDIC spaces (0x40),
truncates from the right if over-length.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging

from interpreter.cobol.ebcdic_table import EbcdicTable

logger = logging.getLogger(__name__)

EBCDIC_SPACE = 0x40


def encode_alphanumeric(value: str, length: int) -> bytes:
    """Encode a string as EBCDIC alphanumeric with fixed length.

    Args:
        value: ASCII string to encode.
        length: Target byte length.

    Returns:
        EBCDIC byte sequence of exactly `length` bytes,
        right-padded with EBCDIC spaces or truncated.
    """
    ebcdic = EbcdicTable.ascii_to_ebcdic(value.encode("ascii", errors="replace"))

    if len(ebcdic) >= length:
        result = ebcdic[:length]
    else:
        result = ebcdic + bytes([EBCDIC_SPACE] * (length - len(ebcdic)))

    logger.debug(
        "encode_alphanumeric(%r, length=%d) → %s",
        value,
        length,
        result.hex(),
    )
    return result


def decode_alphanumeric(data: bytes) -> str:
    """Decode EBCDIC alphanumeric bytes to an ASCII string.

    Args:
        data: EBCDIC byte sequence.

    Returns:
        Decoded ASCII string (trailing EBCDIC spaces become ASCII spaces).
    """
    ascii_bytes = EbcdicTable.ebcdic_to_ascii(data)
    result = ascii_bytes.decode("ascii", errors="replace")

    logger.debug(
        "decode_alphanumeric(%s) → %r",
        data.hex(),
        result,
    )
    return result
