# pyright: standard
"""Decimal math behind COBOL intrinsic functions (moved from byte_builtins, red-dragon-4q25.1).

Semantics are exactly those of the original builtins: arguments coerce through
Decimal (ints, floats via str(), Decimals, numeric text), and division, powers
and SQRT use the default decimal context, as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal, InvalidOperation

from cobol_numeric.number import CobolNumber


def coerce_argument(raw: object) -> CobolNumber | None:
    """ints, floats, Decimals and numeric strings -> Decimal; else None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, Decimal)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


def is_integral(value: CobolNumber) -> bool:
    return value == value.to_integral_value()


def to_result(value: CobolNumber) -> int | CobolNumber:
    """int when integral, else the exact value (NUMVAL's convention)."""
    return int(value) if is_integral(value) else value


def total(values: Sequence[CobolNumber]) -> CobolNumber:
    return sum(values, Decimal(0))


def mean(values: Sequence[CobolNumber]) -> CobolNumber:
    return total(values) / len(values)


def median(values: Sequence[CobolNumber]) -> CobolNumber:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return (
        ordered[mid] if len(ordered) % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2
    )


def midrange(values: Sequence[CobolNumber]) -> CobolNumber:
    return (max(values) + min(values)) / 2


def value_range(values: Sequence[CobolNumber]) -> CobolNumber:
    return max(values) - min(values)


def variance(values: Sequence[CobolNumber]) -> CobolNumber:
    """Sample variance (n - 1 divisor); callers handle n == 1."""
    n = len(values)
    average = total(values) / n
    return sum(((v - average) ** 2 for v in values), Decimal(0)) / (n - 1)


def square_root(value: CobolNumber) -> CobolNumber:
    return value.sqrt()


def absolute(value: CobolNumber) -> CobolNumber:
    return abs(value)


def floor_integer(value: CobolNumber) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def integer_part(value: CobolNumber) -> int:
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def fraction_part(value: CobolNumber) -> CobolNumber:
    return value - value.to_integral_value(rounding=ROUND_DOWN)


def remainder(x: CobolNumber, y: CobolNumber) -> CobolNumber:
    return x - y * (x / y).to_integral_value(rounding=ROUND_DOWN)


def annuity(rate: CobolNumber, periods: int) -> CobolNumber:
    if rate == 0:
        return Decimal(1) / periods
    return rate / (1 - (1 + rate) ** (-periods))


def present_value(rate: CobolNumber, cashflows: Sequence[CobolNumber]) -> CobolNumber:
    return sum(
        (cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows)), Decimal(0)
    )


def parse_numval_digits(text: str, negative: bool) -> int | CobolNumber | None:
    """NUMVAL's cleaned digit text -> int when integral, else exact; None if invalid."""
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return to_result(-parsed if negative else parsed)
