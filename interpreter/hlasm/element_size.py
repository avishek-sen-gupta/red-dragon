# pyright: standard
"""A vector element size, the ES code 0-4 of an M field: its width in bytes and how many elements fill a vector register."""

from enum import Enum

from interpreter.hlasm.hlasm_constants import VECTOR_REGISTER_BYTES


class ElementSize(Enum):
    BYTE = 0
    HALFWORD = 1
    WORD = 2
    DOUBLEWORD = 3
    QUADWORD = 4

    @property
    def width(self) -> int:
        return 1 << self.value

    @property
    def count(self) -> int:
        return VECTOR_REGISTER_BYTES // self.width
