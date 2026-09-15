# pyright: standard
"""Digits stored for a COBOL numeric value — one implementation for every encode path.

The compile-time VALUE path (emit_context.emit_encode_numeric) and the runtime
path (__cobol_prepare_digits / __cobol_prepare_sign) both call ``encode_digits``,
so they cannot diverge again (red-dragon-qhtv, red-dragon-bqds). Exact
arithmetic lives in cobol_numeric; this module only adapts inputs and keeps the
historical tolerance for non-numeric text.
"""

from __future__ import annotations

from cobol_numeric.number import (
    CobolNumber,
    digits_for_encode,
    is_cobol_number,
    scale_by,
    to_number,
)
from cobol_asg.cobol_types import CobolTypeDescriptor
from interpreter.cobol.data_filters import align_decimal, left_adjust


def _parse(value: object) -> CobolNumber | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, float)) or is_cobol_number(value):
        try:
            return to_number(value)
        except ValueError:
            return None
    return None


def encode_digits(
    value: object,
    total_digits: int,
    decimal_digits: int,
    scale: int,
) -> tuple[bool, str]:
    """``(negative, digit_str)`` for ``value`` in a field of the given shape.

    Non-numeric text (spaces, alphanumeric junk) keeps the historical tolerance:
    its characters are aligned as-is and non-digits later become 0.

    Values arrive exact, so they are truncated toward zero with no rounding:
    COBOL truncates unless ROUNDED is given. The guard step 96651c84 added
    here — rounding to ``decimal_digits + 6`` places first, to hide binary
    float noise — is gone with the floats it existed for, and with it the
    bug where genuine nines beyond the scale rounded up (red-dragon-5b93).
    """
    number = _parse(value)
    if number is None:
        text = str(value)
        clean = text.lstrip("+-")
        negative = text.startswith("-") and any(
            ch.isdigit() and ch != "0" for ch in clean
        )
        if decimal_digits > 0:
            return negative, align_decimal(
                clean, total_digits - decimal_digits, decimal_digits
            )
        integer_part = clean.split(".")[0] if "." in clean else clean
        return negative, left_adjust(integer_part, total_digits)
    descaled = scale_by(number, -scale)
    negative, digit_str = digits_for_encode(descaled, total_digits, decimal_digits)
    return negative, digit_str


def descale(value: object, scale: int) -> CobolNumber:
    """Value -> the number the digit positions hold (value / 10^scale)."""
    return scale_by(to_number(value), -scale)


def encode_scaled_digits(value: str, td: CobolTypeDescriptor) -> str:
    """Digit characters stored for ``value`` in a field of type ``td``."""
    _, digit_str = encode_digits(value, td.total_digits, td.decimal_digits, td.scale)
    return digit_str
