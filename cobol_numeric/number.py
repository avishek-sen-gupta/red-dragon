# pyright: standard
"""CobolNumber — the exact representation of COBOL fixed-point values.

All arithmetic is done on exact integer ratios, never through the ``decimal``
context: the default context rounds results to 28 significant digits, while
IBM ARITH(COMPAT) intermediates carry up to 30.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

CobolNumber: TypeAlias = Decimal
NumberLike: TypeAlias = int | Decimal

_ASCII_DIGITS = frozenset("0123456789")


def is_cobol_number(value: object) -> bool:
    """True for exact COBOL numeric values: ``int`` (not ``bool``) or ``CobolNumber``."""
    return not isinstance(value, bool) and isinstance(value, (int, Decimal))


def _exact(value: object) -> Decimal:
    if not is_cobol_number(value):
        raise TypeError(f"not a COBOL number: {value!r}")
    return Decimal(value)  # type: ignore[arg-type]


def _ratio(value: object) -> tuple[int, int]:
    """Exact (numerator, positive denominator)."""
    return _exact(value).as_integer_ratio()


def _from_scaled_int(unscaled: int, decimal_places: int) -> CobolNumber:
    """``unscaled × 10^-decimal_places``, built exactly (string construction is
    not subject to the context precision)."""
    return Decimal(f"{unscaled}E{-decimal_places}")


def _truncate_ratio(
    numerator: int, denominator: int, decimal_places: int
) -> CobolNumber:
    """numerator/denominator truncated toward zero to ``decimal_places``."""
    if decimal_places < 0:
        raise ValueError(f"decimal_places must be >= 0, got {decimal_places}")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    scaled = numerator * 10**decimal_places
    magnitude = abs(scaled) // denominator
    return _from_scaled_int(-magnitude if scaled < 0 else magnitude, decimal_places)


def from_digits(digits: int, decimal_digits: int) -> CobolNumber:
    """Stored digits (sign applied) with ``decimal_digits`` implied places."""
    if decimal_digits < 0:
        raise ValueError(f"decimal_digits must be >= 0, got {decimal_digits}")
    return _from_scaled_int(digits, decimal_digits)


def scale_by(value: NumberLike, scale: int) -> CobolNumber:
    """``value × 10^scale`` (PIC P scaling); an exponent shift, never rounded."""
    sign, digits, exponent = _exact(value).as_tuple()
    assert isinstance(exponent, int)
    return Decimal((sign, digits, exponent + scale))


def from_literal(text: str) -> CobolNumber:
    """Parse a COBOL fixed-point numeric literal: optional sign, digits, at most one '.'."""
    stripped = text.strip()
    body = stripped[1:] if stripped[:1] in ("+", "-") else stripped
    digits = body.replace(".", "", 1)
    if not digits or not set(digits) <= _ASCII_DIGITS:
        raise ValueError(f"not a COBOL fixed-point literal: {text!r}")
    return Decimal(stripped)


def from_float(value: float) -> CobolNumber:
    """The exact decimal of the float's shortest round-trip representation."""
    if not math.isfinite(value):
        raise ValueError(f"non-finite float: {value!r}")
    return Decimal(repr(value))


def to_number(value: object) -> CobolNumber:
    """Normalise an arithmetic operand: exact numbers, floats, or numeric text."""
    if isinstance(value, float):
        return from_float(value)
    if isinstance(value, str):
        return from_literal(value)
    return _exact(value)


def to_float(value: NumberLike) -> float:
    return float(_exact(value))


def truncate_to(value: NumberLike, decimal_places: int) -> CobolNumber:
    return _truncate_ratio(*_ratio(value), decimal_places)


def round_half_up(value: NumberLike, decimal_places: int) -> CobolNumber:
    """Round to ``decimal_places``, ties away from zero (COBOL ROUNDED)."""
    numerator, denominator = _ratio(value)
    magnitude = (2 * abs(numerator) * 10**decimal_places + denominator) // (
        2 * denominator
    )
    return _from_scaled_int(-magnitude if numerator < 0 else magnitude, decimal_places)


def add(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bd + bn * ad, ad * bd, result_decimals)


def subtract(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bd - bn * ad, ad * bd, result_decimals)


def multiply(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bn, ad * bd, result_decimals)


def divide(
    dividend: NumberLike, divisor: NumberLike, quotient_decimals: int
) -> CobolNumber:
    an, ad = _ratio(dividend)
    bn, bd = _ratio(divisor)
    if bn == 0:
        raise ZeroDivisionError("COBOL division by zero")
    return _truncate_ratio(an * bd, ad * bn, quotient_decimals)


def digits_for_encode(
    value: NumberLike, total_digits: int, decimal_digits: int, scale: int = 0
) -> tuple[bool, str]:
    """``(negative, digit_str)`` stored for ``value`` in a field of ``total_digits``
    with ``decimal_digits`` implied places and PIC P ``scale``.

    Divides by the scaling factor, truncates toward zero to ``decimal_digits``,
    and keeps the low-order ``total_digits`` (COBOL high-order truncation).
    ``negative`` is the sign of the value before truncation, matching the
    runtime sign-nibble builtin (a value like -0.001 keeps a negative sign).
    """
    exact = _exact(value)
    scaled = scale_by(exact, -scale)
    if scale < 0:
        # Negative scale: don't truncate; scale by (decimal_digits - scale)
        unscaled = abs(int(scale_by(scaled, decimal_digits - scale)))
    else:
        # Non-negative scale: truncate then scale by decimal_digits
        stored = truncate_to(scaled, decimal_digits)
        unscaled = abs(int(scale_by(stored, decimal_digits)))
    digit_str = (
        str(unscaled).rjust(total_digits, "0")[-total_digits:] if total_digits else ""
    )
    return exact < 0, digit_str


def to_plain_str(value: NumberLike) -> str:
    """Plain decimal text: optional '-', digits, optional '.' and digits; never an exponent."""
    return format(_exact(value), "f")


def as_whole_int(value: NumberLike) -> int | None:
    numerator, denominator = _ratio(value)
    return numerator if denominator == 1 else None
