"""How a SORT or MERGE key's bytes are read for comparison."""

from __future__ import annotations

from enum import Enum


class SortKeyEncoding(Enum):
    ALPHANUMERIC = "ALPHANUMERIC"
