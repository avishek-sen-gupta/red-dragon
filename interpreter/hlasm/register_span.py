# pyright: standard
"""The bit positions of a register that a ROTATE THEN ... SELECTED BITS field selects within, numbered from the leftmost bit."""

from collections.abc import Iterable
from dataclasses import dataclass

from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, WORD_BITS


def _bits_at(positions: Iterable[int]) -> int:
    return sum(1 << (DOUBLEWORD_BITS - 1 - position) for position in positions)


@dataclass(frozen=True)
class RegisterSpan:
    """A run of bit positions starting at `origin`; a range within it wraps from its last position to its first."""

    origin: int
    bits: int

    def position(self, field: int) -> int:
        return self.origin + (field & (self.bits - 1))

    def word(self) -> int:
        return _bits_at(range(self.origin, self.origin + self.bits))

    def selected(self, start_field: int, end_field: int) -> int:
        start = self.position(start_field) - self.origin
        count = (self.position(end_field) - self.origin - start) % self.bits + 1
        return _bits_at(
            self.origin + (start + step) % self.bits for step in range(count)
        )


WHOLE_REGISTER = RegisterSpan(0, DOUBLEWORD_BITS)
HIGH_WORD = RegisterSpan(0, WORD_BITS)
LOW_WORD = RegisterSpan(WORD_BITS, WORD_BITS)
