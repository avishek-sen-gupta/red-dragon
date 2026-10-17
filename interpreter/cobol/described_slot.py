"""A variable-length relative slot: a 4-byte record descriptor word (the length
with itself, big-endian, then 2 reserved bytes), the record, then zero padding to
the file's maximum record length."""

from __future__ import annotations

from interpreter.cobol.relative_slot import RelativeSlot

_RDW = 4


class DescribedSlot(RelativeSlot):
    def size(self, record_length: int) -> int:
        return _RDW + record_length

    def packed(self, data: bytes, record_length: int) -> bytes:
        record = data[:record_length]
        rdw = (len(record) + _RDW).to_bytes(2, "big") + bytes(2)
        return rdw + record.ljust(record_length, b"\x00")

    def record(self, slot: bytes) -> tuple[bytes, ...]:
        length = int.from_bytes(slot[:2], "big")
        return (slot[_RDW:length],) if length else ()

    def vacant(self) -> bytes:
        return bytes(_RDW)
