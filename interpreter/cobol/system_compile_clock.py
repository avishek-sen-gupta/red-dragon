"""The machine's local time with its offset from Greenwich mean time."""

from __future__ import annotations

from datetime import datetime

from interpreter.cobol.compile_clock import CompileClock


class SystemCompileClock(CompileClock):
    def now(self) -> datetime:
        return datetime.now().astimezone()
