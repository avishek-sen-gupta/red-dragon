"""LP — IBM's pointer-width compile option."""

from __future__ import annotations

from enum import Enum


class LP(Enum):
    LP32 = "LP(32)"
    LP64 = "LP(64)"
