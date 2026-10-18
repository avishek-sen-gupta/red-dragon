"""The clock a COBOL compile reads once, for FUNCTION WHEN-COMPILED."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class CompileClock(Protocol):
    def now(self) -> datetime: ...
