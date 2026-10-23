# pyright: standard
"""The clock an HLASM assembly reads once, for &SYSDATE, &SYSDATC, &SYSTIME and &SYSCLOCK; COBOL's CompileClock, which this package cannot import."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class AssemblyClock(Protocol):
    def now(self) -> datetime: ...
