# pyright: standard
"""A BFP format as it sits in floating-point registers: its zarch_float format, image width and builtin suffix."""

from dataclasses import dataclass

from interpreter.hlasm.fpr_layout import FprLayout
from zarch_float.bfp_format import EXTENDED, LONG, SHORT, BfpFormat


@dataclass(frozen=True)
class BfpLayout(FprLayout):
    format: BfpFormat
    width: int
    suffix: str

    @property
    def fraction_bits(self) -> int:
        return self.format.precision - 1

    @property
    def exponent_mask(self) -> int:
        return 2 * self.format.emax + 1

    @property
    def sign_shift(self) -> int:
        return self.width - 1

    @property
    def magnitude_mask(self) -> int:
        return (1 << self.sign_shift) - 1

    @property
    def infinity(self) -> int:
        return self.exponent_mask << self.fraction_bits

    @property
    def quiet_bit(self) -> int:
        return 1 << (self.fraction_bits - 1)


SHORT_LAYOUT = BfpLayout(SHORT, 32, "short")
LONG_LAYOUT = BfpLayout(LONG, 64, "long")
EXTENDED_LAYOUT = BfpLayout(EXTENDED, 128, "extended")
