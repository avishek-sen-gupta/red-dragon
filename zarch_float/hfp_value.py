# pyright: standard
"""An HFP number: 0.fraction x 16**exponent, the exponent unbounded (characteristic - 64)."""

from dataclasses import dataclass, replace
from fractions import Fraction

from zarch_float.hfp_format import HfpFormat


@dataclass(frozen=True)
class HfpValue:
    format: HfpFormat
    negative: bool
    fraction: int
    exponent: int

    def magnitude(self) -> Fraction:
        return self.fraction * Fraction(16) ** (self.exponent - self.format.digits)

    def negated(self) -> "HfpValue":
        return replace(self, negative=not self.negative)
