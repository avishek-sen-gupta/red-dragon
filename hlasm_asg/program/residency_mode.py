# pyright: standard
"""An RMODE operand."""

from __future__ import annotations

from enum import StrEnum


class ResidencyMode(StrEnum):
    RMODE_24 = "24"
    RMODE_31 = "31"
    RMODE_64 = "64"
    ANY = "ANY"
