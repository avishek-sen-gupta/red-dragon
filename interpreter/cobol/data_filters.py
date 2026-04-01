# pyright: standard
"""Data alignment filters for COBOL numeric formatting.

Ported from smojol's RightAdjuster, LeftAdjuster, DecimalPointAligner.
Pure functions — zero dependencies.
"""

from __future__ import annotations


def right_adjust(value: str, length: int) -> str:
    """Right-pad with spaces, truncate from right if over-length.

    Used for alphanumeric fields: value is placed left-justified,
    padded or truncated to exactly `length` characters.
    """
    padded = value.ljust(length)
    return padded[:length]


def left_adjust(value: str, length: int) -> str:
    """Left-pad with zeros, keep rightmost `length` chars if over-length.

    Used for numeric fields: value is right-justified with leading zeros.
    If longer than length, leftmost digits are truncated (overflow).
    """
    padded = value.zfill(length)
    return padded[-length:] if len(padded) > length else padded


def align_decimal(value: str, integer_digits: int, decimal_digits: int) -> str:
    """Split at decimal point, align both halves, concatenate without dot.

    Integer part: left-adjusted (zero-padded) to integer_digits.
    Decimal part: right-adjusted (space-padded, but we use zero-pad) to decimal_digits.
    If no decimal point, treat entire value as integer part with zero decimal.
    """
    if "." in value:
        parts = value.split(".", 1)
        int_part = parts[0]
        dec_part = parts[1]
    else:
        int_part = value
        dec_part = ""

    aligned_int = left_adjust(int_part, integer_digits)
    # Decimal part: right-pad with zeros and truncate from right
    dec_padded = dec_part.ljust(decimal_digits, "0")
    aligned_dec = dec_padded[:decimal_digits]

    return aligned_int + aligned_dec
