"""An FD without a LINAGE clause: its file has no logical page."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoLinage:
    """No LINAGE clause, so no LINAGE-COUNTER and no end-of-page condition."""


NO_LINAGE = NoLinage()
