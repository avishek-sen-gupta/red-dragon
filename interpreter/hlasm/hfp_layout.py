# pyright: standard
"""An HFP format as it sits in floating-point registers: its zarch_float format, image width and builtin suffix."""

from dataclasses import dataclass

from interpreter.hlasm.fpr_layout import FprLayout
from zarch_float.hfp_format import EXTENDED, LONG, SHORT, HfpFormat

CHARACTERISTIC_BITS = 7
CHARACTERISTIC_MASK = (1 << CHARACTERISTIC_BITS) - 1
EXCESS = 64
PART_WIDTH = 64
PART_FRACTION_BITS = 56


@dataclass(frozen=True)
class HfpLayout(FprLayout):
    format: HfpFormat
    width: int
    suffix: str

    @property
    def sign_shift(self) -> int:
        return self.width - 1

    @property
    def characteristic_shift(self) -> int:
        return self.width - 1 - CHARACTERISTIC_BITS

    @property
    def fraction_bits(self) -> int:
        return 4 * self.format.digits

    @property
    def fraction_mask(self) -> int:
        part = (1 << min(self.fraction_bits, PART_FRACTION_BITS)) - 1
        return part << PART_WIDTH | part if self.width > PART_WIDTH else part


SHORT_HFP = HfpLayout(SHORT, 32, "short")
LONG_HFP = HfpLayout(LONG, 64, "long")
EXTENDED_HFP = HfpLayout(EXTENDED, 128, "extended")
