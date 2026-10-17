"""How one slot of a relative file holds its record, or marks itself empty."""

from __future__ import annotations

from typing import Protocol


class RelativeSlot(Protocol):
    def size(self, record_length: int) -> int: ...

    def packed(self, data: bytes, record_length: int) -> bytes: ...

    def record(self, slot: bytes) -> tuple[bytes, ...]: ...

    def vacant(self) -> bytes: ...
