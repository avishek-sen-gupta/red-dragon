# pyright: standard
"""Bytes of a DC operand that are known when the program is assembled."""

from dataclasses import dataclass

from interpreter.hlasm.dc_warning import DcWarning


@dataclass(frozen=True)
class ConstantImage:
    image: tuple[int, ...]
    warnings: tuple[DcWarning, ...] = ()

    @property
    def width(self) -> int:
        return len(self.image)
