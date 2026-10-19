"""A LINAGE clause without WITH FOOTING: its page body has no footing area."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoFooting:
    """No footing area: only page overflow reaches the end of the page."""


NO_FOOTING = NoFooting()
