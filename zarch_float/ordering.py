# pyright: standard
"""Orders two exact ranks as a comparison outcome."""

from fractions import Fraction

from zarch_float.comparison import Comparison

_OUTCOMES = {0: Comparison.EQUAL, -1: Comparison.LOW, 1: Comparison.HIGH}


def ordered(a: tuple[int, Fraction], b: tuple[int, Fraction]) -> Comparison:
    return _OUTCOMES[(a > b) - (a < b)]
