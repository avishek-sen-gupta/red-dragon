"""A delimiter's characters as UNSTRING scans for them, and whether ALL folds a
run of contiguous occurrences into one."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnstringDelimiterText:
    text: str
    all: bool
