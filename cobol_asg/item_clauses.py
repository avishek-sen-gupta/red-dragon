"""The clauses of one data description entry that shape its picture's type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemClauses:
    """SIGN IS LEADING / SEPARATE, JUSTIFIED RIGHT and BLANK WHEN ZERO, as the item takes them."""

    sign_leading: bool = False
    sign_separate: bool = False
    justified_right: bool = False
    blank_when_zero: bool = False


NO_ITEM_CLAUSES = ItemClauses()
