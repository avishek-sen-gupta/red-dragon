"""WarnAndIgnore — a NULL-page read gives zeroes and a write is dropped, both logged."""

from __future__ import annotations

import logging

from interpreter.vm.null_access import NullAccess

_LOG = logging.getLogger(__name__)


class WarnAndIgnore(NullAccess):
    def on_read(self, address: int, length: int) -> bytes:
        _LOG.warning("read of %d bytes at NULL-page address %d", length, address)
        return bytes(length)

    def on_write(self, address: int, length: int) -> None:
        _LOG.warning(
            "write of %d bytes at NULL-page address %d dropped", length, address
        )


WARN_AND_IGNORE = WarnAndIgnore()
