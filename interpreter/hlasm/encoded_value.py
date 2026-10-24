# pyright: standard
"""One DC value's image as an integer of its bit length, with the warnings its conversion raised."""

from dataclasses import dataclass

from interpreter.hlasm.dc_warning import DcWarning


@dataclass(frozen=True)
class EncodedValue:
    value: int
    warnings: tuple[DcWarning, ...] = ()
