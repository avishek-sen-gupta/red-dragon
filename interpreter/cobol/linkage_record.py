"""A LINKAGE 01 in the section's static, end-to-end layout."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkageRecord:
    """Where a LINKAGE 01 sits in the static layout analysis extents use."""

    name: str
    start: int
    length: int
