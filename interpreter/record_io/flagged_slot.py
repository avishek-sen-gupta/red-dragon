"""A fixed-length relative slot: a presence flag byte, then the record."""

from __future__ import annotations

from interpreter.record_io.relative_slot import RelativeSlot

_ACTIVE = b"\xff"
_EMPTY = b"\x00"


class FlaggedSlot(RelativeSlot):
    def size(self, record_length: int) -> int:
        return 1 + record_length

    def packed(self, data: bytes, record_length: int) -> bytes:
        return _ACTIVE + data[:record_length].ljust(record_length)

    def record(self, slot: bytes) -> tuple[bytes, ...]:
        return (slot[1:],) if slot[:1] == _ACTIVE else ()

    def vacant(self) -> bytes:
        return _EMPTY
