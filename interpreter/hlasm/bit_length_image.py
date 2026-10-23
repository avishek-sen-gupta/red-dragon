# pyright: standard
"""The values of a bit-length DC operand (L.n), each n bits wide, packed from the operand's bit offset."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BitLengthImage:
    values: tuple[int, ...]
    bits: int
