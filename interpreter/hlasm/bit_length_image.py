# pyright: standard
"""The values of a bit-length DC operand (L.n), each n bits wide, packed from the operand's bit offset."""

from dataclasses import dataclass

from interpreter.hlasm.dc_warning import DcWarning


@dataclass(frozen=True)
class BitLengthImage:
    values: tuple[int, ...]
    bits: int
    warnings: tuple[DcWarning, ...] = ()
