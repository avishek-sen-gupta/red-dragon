# pyright: standard
"""IBM ARITH(COMPAT) places carried for fixed-point intermediate results.

Source: IBM COBOL reference "Fixed-point data and intermediate results"
(rpinr04) and "Terminology used for intermediate results" (rpinr03). In a
division, op1 is the divisor and op2 the dividend.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPAT_DIGIT_LIMIT = 30


@dataclass(frozen=True)
class Scale:
    integer_places: int
    decimal_places: int


def add_scale(a: Scale, b: Scale) -> Scale:
    return Scale(
        max(a.integer_places, b.integer_places) + 1,
        max(a.decimal_places, b.decimal_places),
    )


def mul_scale(a: Scale, b: Scale) -> Scale:
    return Scale(
        a.integer_places + b.integer_places, a.decimal_places + b.decimal_places
    )


def div_scale(dividend: Scale, divisor: Scale, dmax: int) -> Scale:
    return Scale(
        dividend.integer_places + divisor.decimal_places,
        max(dividend.decimal_places - divisor.decimal_places, dmax),
    )


def carry(scale: Scale, dmax: int, limit: int = COMPAT_DIGIT_LIMIT) -> Scale:
    i, d = scale.integer_places, scale.decimal_places
    if i + d <= limit:
        return scale
    if d <= dmax:
        return Scale(limit - d, d)
    if i + dmax <= limit:
        return Scale(i, limit - i)
    return Scale(limit - dmax, dmax)


def literal_scale(text: str) -> Scale:
    body = text.strip().lstrip("+-")
    integer_part, _, fraction_part = body.partition(".")
    return Scale(max(len(integer_part), 1), len(fraction_part))
