# pyright: standard
"""Bytes of a DC operand that are known when the program is assembled."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstantImage:
    image: tuple[int, ...]

    @property
    def width(self) -> int:
        return len(self.image)
