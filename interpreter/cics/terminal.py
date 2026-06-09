"""Terminal-channel protocols for the CICS region's screen/input seams.

The running region only touches its two terminal queues through a tiny surface:

  * the **outbound screen channel** receives rendered screen payloads — the
    region ``put``s them (SEND MAP / SEND TEXT) and a terminal/driver consumes
    them;
  * the **inbound input channel** carries terminal input events — a
    terminal/driver ``put``s them and the region ``get``s them (RECEIVE MAP,
    blocking with an optional timeout).

Those two operations are all the region needs, so they are captured here as
``typing.Protocol``s. ``queue.Queue`` structurally conforms to both, which is
how the region runs **in-process today** with zero call-site or test changes.

An **external / out-of-process producer** (a ``multiprocessing.Queue``, or a
socket / websocket transport) can drive the same region by implementing these
protocols over its wire: it ``put``s input events and ``get``s nothing on the
input side from the producer's perspective, and consumes screen payloads off
the screen side. The payloads are terminal-shaped, JSON-serialisable messages:
the screen channel carries plain dicts (``{"map": ..., "fields": {...}}`` for
SEND MAP, ``{"type": "text", "text": ...}`` for SEND TEXT) and the input
channel carries ``InputEvent`` values (attention key + field map), so a remote
transport can serialise/deserialise them across the boundary.

Note: the input item is kept ``Any`` rather than importing ``InputEvent`` from
``interpreter.cics.dispatcher`` — dispatcher imports these protocols, so naming
``InputEvent`` here would create an import cycle. In practice the item is an
``InputEvent`` (or, for legacy producers, a plain field dict).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ScreenChannel(Protocol):
    """Outbound terminal channel.

    The CICS region ``put``s rendered screen payloads (dicts) here; a
    terminal / driver / external transport consumes them. ``queue.Queue``
    satisfies this.
    """

    def put(self, item: Any) -> None: ...


@runtime_checkable
class InputChannel(Protocol):
    """Inbound terminal channel.

    The region ``get``s terminal input events here (RECEIVE MAP — blocking,
    with an optional timeout); a terminal / driver / external transport
    ``put``s them. The ``get`` signature mirrors ``queue.Queue.get``
    (``block=True, timeout=None``) so ``queue.Queue`` conforms cleanly and the
    region's ``.get()`` / ``.get(timeout=...)`` calls are both compatible.
    """

    def put(self, item: Any) -> None: ...

    def get(self, block: bool = True, timeout: float | None = None) -> Any: ...
