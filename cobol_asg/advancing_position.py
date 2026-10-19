"""Whether a WRITE prints its line before or after the device advances."""

from __future__ import annotations

from enum import StrEnum


class AdvancingPosition(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
