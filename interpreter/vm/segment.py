"""Segment — where one region sits in the flat address space."""

from __future__ import annotations

from dataclasses import dataclass

FIRST_ADDRESS = 4096


@dataclass(frozen=True)
class Segment:
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size

    def overlap(self, address: int, length: int) -> tuple[int, int]:
        """The part of [address, address + length) inside this segment, as
        offsets into the segment; empty when they do not meet."""
        start = max(address, self.base)
        stop = min(address + length, self.end)
        return (start - self.base, max(stop, start) - self.base)
