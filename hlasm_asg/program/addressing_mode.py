# pyright: standard
"""An AMODE operand."""

from __future__ import annotations

from enum import StrEnum


class AddressingMode(StrEnum):
    AMODE_24 = "24"
    AMODE_31 = "31"
    AMODE_64 = "64"
    ANY = "ANY"
    ANY31 = "ANY31"
    ANY64 = "ANY64"
