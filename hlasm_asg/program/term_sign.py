# pyright: standard
"""Whether a relocatable term of a complex-relocatable value is added or subtracted."""

from __future__ import annotations

from enum import StrEnum


class TermSign(StrEnum):
    PLUS = "PLUS"
    MINUS = "MINUS"
