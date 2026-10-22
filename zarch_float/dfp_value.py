# pyright: standard
"""A DFP datum in the right-units view: significand x 10**exponent, or a NaN's payload."""

from dataclasses import dataclass, replace
from fractions import Fraction

from zarch_float.dfp_format import DfpFormat
from zarch_float.float_kind import FloatKind


@dataclass(frozen=True)
class DfpValue:
    format: DfpFormat
    negative: bool
    kind: FloatKind
    significand: int = 0
    exponent: int = 0

    def magnitude(self) -> Fraction:
        return self.significand * Fraction(10) ** self.exponent

    def signed(self) -> Fraction:
        return -self.magnitude() if self.negative else self.magnitude()

    def negated(self) -> "DfpValue":
        return replace(self, negative=not self.negative)

    def is_nan(self) -> bool:
        return self.kind in (FloatKind.QNAN, FloatKind.SNAN)

    def is_finite(self) -> bool:
        return self.kind in (FloatKind.ZERO, FloatKind.FINITE)
