# pyright: standard
"""An HFP format: the number of hexadecimal fraction digits."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HfpFormat:
    digits: int


SHORT = HfpFormat(6)
LONG = HfpFormat(14)
EXTENDED = HfpFormat(28)
