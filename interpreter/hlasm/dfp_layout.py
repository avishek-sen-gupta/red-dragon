# pyright: standard
"""A DFP format as it sits in floating-point registers: its zarch_float format, image width, exponent continuation and declets (PoO figure 20-3)."""

from dataclasses import dataclass

from interpreter.hlasm.fpr_layout import FprLayout
from zarch_float.dfp_format import EXTENDED, LONG, SHORT, DfpFormat

DECLET_BITS = 10
COMBINATION_TOP_BITS = 5
TOP_EXPONENT_VALUES = 3


@dataclass(frozen=True)
class DfpLayout(FprLayout):
    format: DfpFormat
    width: int
    suffix: str
    continuation_bits: int

    @property
    def bias(self) -> int:
        return self.format.bias

    @property
    def max_biased_exponent(self) -> int:
        return (TOP_EXPONENT_VALUES << self.continuation_bits) - 1

    @property
    def trailing_digits(self) -> int:
        return self.format.precision - 1

    @property
    def declets(self) -> int:
        return self.trailing_digits // 3

    @property
    def trailing_bits(self) -> int:
        return DECLET_BITS * self.declets

    @property
    def sign_shift(self) -> int:
        return self.width - 1

    @property
    def top_shift(self) -> int:
        return self.sign_shift - COMBINATION_TOP_BITS

    @property
    def continuation_shift(self) -> int:
        return self.top_shift - self.continuation_bits


SHORT_DFP = DfpLayout(SHORT, 32, "short", 6)
LONG_DFP = DfpLayout(LONG, 64, "long", 8)
EXTENDED_DFP = DfpLayout(EXTENDED, 128, "extended", 12)
