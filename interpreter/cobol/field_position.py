# pyright: standard
"""Where a WORKING-STORAGE field sits and how it is stored, as the layout Data declares it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldPosition:
    offset: int
    length: int
    category: str
    total_digits: int
    decimal_digits: int
    signed: bool
