# pyright: standard
"""A floating-point DC nominal written as a number: sign, decimal coefficient and exponent as written (with the exponent modifier), and the rounding mode it selects."""

from dataclasses import dataclass
from fractions import Fraction

_DECIMAL_BASE = Fraction(10)
_EXPONENT_PAST_EVERY_FORMAT = 20_000


@dataclass(frozen=True)
class FloatNumber:
    negative: bool
    coefficient: int
    fraction_digits: int
    written_exponent: int
    rounding: int

    @property
    def exponent(self) -> int:
        exponent = self.written_exponent - self.fraction_digits
        return max(
            -_EXPONENT_PAST_EVERY_FORMAT, min(_EXPONENT_PAST_EVERY_FORMAT, exponent)
        )

    def magnitude(self) -> Fraction:
        return self.coefficient * _DECIMAL_BASE**self.exponent
