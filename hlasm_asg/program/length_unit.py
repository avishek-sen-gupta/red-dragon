# pyright: standard
"""The unit of a DC or DS operand's length: bytes, or bits when written L.n."""

from __future__ import annotations

from enum import StrEnum


class LengthUnit(StrEnum):
    BYTE = "BYTE"
    BIT = "BIT"
