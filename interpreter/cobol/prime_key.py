"""Where an indexed file's prime record key lies in its records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrimeKey:
    offset: int = 0
    length: int = 0

    def of(self, record: bytes) -> bytes:
        return record[self.offset : self.offset + self.length]
