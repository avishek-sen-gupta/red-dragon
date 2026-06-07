# pyright: standard
"""Alphanumeric encoding/decoding — reference implementation.

Ported from smojol's AlphanumericDataTypeSpec.java.
Uses EBCDIC encoding, right-pads with EBCDIC spaces (0x40),
truncates from the right if over-length.

This is a reference implementation for testing — NOT a VM builtin.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import ByteConstants
from interpreter.cobol.ebcdic_table import EbcdicTable

logger = logging.getLogger(__name__)

EBCDIC_SPACE = ByteConstants.EBCDIC_SPACE


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


def parse_hex_literal(value: str) -> bytes | None:
    """Parse a COBOL hex literal of the form X'..' / x'..' into raw bytes.

    Returns the decoded raw bytes, or ``None`` if ``value`` is not a
    well-formed hex literal (i.e. it should be treated as an ordinary
    alphanumeric VALUE and go through ASCII→EBCDIC translation).

    A valid hex literal is ``X`` or ``x``, a single quote, an even number of
    hex digits, and a closing single quote: e.g. ``X'7D'`` → ``b'\\x7d'``,
    ``X'C1C2'`` → ``b'\\xc1\\xc2'``.
    """
    if len(value) < 4 or value[0] not in ("X", "x"):
        return None
    if value[1] != "'" or value[-1] != "'":
        return None
    inner = value[2:-1]
    if len(inner) == 0 or len(inner) % 2 != 0:
        return None
    try:
        return bytes.fromhex(inner)
    except ValueError:
        return None


def encode_hex_literal(raw: bytes, length: int) -> bytes:
    """Place raw hex-literal bytes into a fixed-length alphanumeric field.

    Raw bytes are stored verbatim (no EBCDIC translation), left-justified and
    right-padded with EBCDIC spaces, or truncated from the right if over-length
    — matching COBOL alphanumeric VALUE semantics.
    """
    if len(raw) >= length:
        return raw[:length]
    return raw + bytes([EBCDIC_SPACE] * (length - len(raw)))


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
