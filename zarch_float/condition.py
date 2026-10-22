# pyright: standard
"""Exception conditions a floating-point operation can raise, reported as data."""

from enum import Enum


class Condition(Enum):
    INVALID = "invalid"
    DIVISION_BY_ZERO = "division-by-zero"
    OVERFLOW = "overflow"
    UNDERFLOW = "underflow"
    TINY = "tiny"
    INEXACT = "inexact"
    INCREMENTED = "incremented"
    QUANTUM = "quantum"
    HFP_EXPONENT_OVERFLOW = "hfp-exponent-overflow"
    HFP_EXPONENT_UNDERFLOW = "hfp-exponent-underflow"
    HFP_SIGNIFICANCE = "hfp-significance"
    HFP_DIVIDE = "hfp-divide"
    HFP_SQUARE_ROOT = "hfp-square-root"
    OUT_OF_RANGE = "out-of-range"


def raised(*checks: tuple[Condition, bool]) -> frozenset[Condition]:
    return frozenset(condition for condition, holds in checks if holds)
