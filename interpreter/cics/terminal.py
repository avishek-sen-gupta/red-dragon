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

Both ends of either channel speak exactly one tiny surface — ``put`` and
``get`` — so the protocol is a single shape (``ScreenChannel`` and
``InputChannel`` are readable aliases for that one surface). The ``get``
signature mirrors ``queue.Queue.get`` (``block=True, timeout=None``), which
covers all three access modes a consumer needs:

  * blocking ``get()`` (region RECEIVE MAP),
  * timed ``get(timeout=...)`` (region RECEIVE MAP with a deadline), and
  * non-blocking ``get(block=False)`` (driver/test screen drains).

The **"no item available" signal is** :class:`queue.Empty` (stdlib): both
``queue.Queue`` and any external / transport-backed channel must raise
``queue.Empty`` from a non-blocking or timed-out ``get`` when no item is
available. Drains therefore loop ``get(block=False)`` and catch ``queue.Empty``
— there is no ``get_nowait`` / ``empty`` / ``qsize`` in the protocol. The
region itself only ``put``s on the screen channel and ``get``s on the input
channel; the driver does the reverse. ``queue.Queue`` structurally conforms to
the whole surface, which is how the region runs **in-process today** with zero
call-site or test changes.

Note: the input item is kept ``Any`` rather than importing ``InputEvent`` from
``interpreter.cics.dispatcher`` — dispatcher imports these protocols, so naming
``InputEvent`` here would create an import cycle. In practice the item is an
``InputEvent`` (or, for legacy producers, a plain field dict).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class _TerminalChannel(Protocol):
    """The single terminal-channel surface: ``put`` + ``get``.

    Both directions of a CICS terminal seam expose exactly these two operations,
    matching ``queue.Queue`` so it conforms structurally. ``ScreenChannel`` and
    ``InputChannel`` below are readable aliases for this one shape (a producer
    typically only ``put``s, a consumer only ``get``s — but the surface is the
    same on both ends, so the channel is fully swappable end-to-end).

    ``get`` mirrors ``queue.Queue.get`` (``block=True, timeout=None``) and raises
    :class:`queue.Empty` when no item is available on a non-blocking/timed call;
    drains loop ``get(block=False)`` and catch ``queue.Empty``.
    """

    def put(self, item: Any) -> None: ...

    def get(self, block: bool = True, timeout: float | None = None) -> Any: ...


# Readable, role-naming aliases for the single put/get surface above. The region
# only ``put``s on the ScreenChannel and only ``get``s on the InputChannel; the
# driver/terminal does the reverse. Both are the same protocol so either end can
# be backed by queue.Queue or by any external/transport-backed channel.
ScreenChannel = _TerminalChannel
InputChannel = _TerminalChannel
