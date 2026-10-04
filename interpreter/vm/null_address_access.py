"""NullAddressAccess — raised when a run halts on a NULL-page access."""

from __future__ import annotations


class NullAddressAccess(Exception):
    def __init__(self, address: int, length: int) -> None:
        super().__init__(f"{length} bytes at NULL-page address {address}")
