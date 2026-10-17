"""An I-O status key 1 value that a USE procedure is not triggered by on its own."""

from __future__ import annotations

from enum import Enum


class StatusClass(Enum):
    SUCCESSFUL = "0"
    AT_END = "1"
    INVALID_KEY = "2"
