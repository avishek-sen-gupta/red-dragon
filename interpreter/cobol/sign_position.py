"""Where a signed zoned item's operational sign sits in its stored bytes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignPosition:
    """The index of the byte carrying the sign, and whether that byte is a
    separate sign character rather than a digit with an overpunched zone."""

    index: int
    separate: bool
