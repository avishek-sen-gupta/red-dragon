# pyright: standard
"""A BFP datum: significand x 2**exponent, or a NaN whose significand is its payload."""

from dataclasses import dataclass, replace
from fractions import Fraction

from zarch_float.bfp_format import BfpFormat
from zarch_float.float_kind import FloatKind


@dataclass(frozen=True)
class BfpValue:
    format: BfpFormat
    negative: bool
    kind: FloatKind
    significand: int = 0
    exponent: int = 0

    def magnitude(self) -> Fraction:
        return self.significand * Fraction(2) ** self.exponent

    def signed(self) -> Fraction:
        return -self.magnitude() if self.negative else self.magnitude()

    def negated(self) -> "BfpValue":
        return replace(self, negative=not self.negative)

    def is_nan(self) -> bool:
        return self.kind in (FloatKind.QNAN, FloatKind.SNAN)
