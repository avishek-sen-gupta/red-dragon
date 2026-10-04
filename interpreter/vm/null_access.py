"""NullAccess — what the VM does with a read or write below the first address."""

from __future__ import annotations

from typing import Protocol


class NullAccess(Protocol):
    def on_read(self, address: int, length: int) -> bytes: ...

    def on_write(self, address: int, length: int) -> None: ...
