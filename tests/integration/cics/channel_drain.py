"""Shared drain helper for CICS terminal-channel tests.

The CICS screen/input seams are typed to the ``ScreenChannel`` / ``InputChannel``
protocols, whose only operations are ``put`` and ``get(block=True,
timeout=None)``. Tests therefore drain a screen channel through the protocol's
``get`` — looping ``get(block=False)`` and catching :class:`queue.Empty` — rather
than reaching for ``queue.Queue``-specific ``get_nowait`` / ``empty`` / ``qsize``.

This keeps BOTH ends of the channel (the region AND the driver/tests) on the same
put/get surface, so any protocol-conforming channel (not just ``queue.Queue``)
works unchanged.
"""

from __future__ import annotations

import queue
from typing import Any


def drain(channel: Any, *, _empty: type[BaseException] = queue.Empty) -> list[Any]:
    """Drain every currently-available item from ``channel`` via the protocol.

    Loops ``channel.get(block=False)`` until the channel signals emptiness by
    raising :class:`queue.Empty`, then returns the items in the order they were
    received. Equivalent to the old ``while not q.empty(): out.append(q.get_nowait())``
    idiom, but expressed purely through the put/get channel protocol.
    """
    out: list[Any] = []
    while True:
        try:
            out.append(channel.get(block=False))
        except _empty:
            break
    return out
