"""The order a SORT or MERGE key places records in."""

from __future__ import annotations

from enum import Enum


class SortKeyDirection(Enum):
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"
