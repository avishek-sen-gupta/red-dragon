"""The files a SORT or MERGE reads its records from (USING) or writes them to (GIVING)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SortFiles:
    names: tuple[str, ...]
