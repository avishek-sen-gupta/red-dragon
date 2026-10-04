"""HaltOnNull — a NULL-page access stops the run, as S0C4 would."""

from __future__ import annotations

from interpreter.vm.null_access import NullAccess
from interpreter.vm.null_address_access import NullAddressAccess


class HaltOnNull(NullAccess):
    def on_read(self, address: int, length: int) -> bytes:
        raise NullAddressAccess(address, length)

    def on_write(self, address: int, length: int) -> None:
        raise NullAddressAccess(address, length)
