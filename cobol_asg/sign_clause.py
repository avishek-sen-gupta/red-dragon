# pyright: standard
"""A SIGN clause as an entry writes it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_LEADING = "LEADING"


@dataclass(frozen=True)
class SignClause:
    """The clause's position and SEPARATE phrase; ``written`` is false when the entry has none."""

    written: bool
    leading: bool
    separate: bool

    @classmethod
    def from_dict(cls, data: Mapping) -> SignClause:
        if "sign" not in data:
            return NO_SIGN_CLAUSE
        sign = data["sign"]
        return cls(
            written=True,
            leading=sign.get("position", "") == _LEADING,
            separate=sign.get("separate", False),
        )

    def nearest(self, enclosing: SignClause) -> SignClause:
        """This clause when written, else the nearest enclosing group's."""
        return self if self.written else enclosing


NO_SIGN_CLAUSE = SignClause(written=False, leading=False, separate=False)
