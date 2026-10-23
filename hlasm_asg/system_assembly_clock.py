# pyright: standard
"""The machine's local time with its offset from UTC."""

from __future__ import annotations

from datetime import datetime

from hlasm_asg.assembly_clock import AssemblyClock


class SystemAssemblyClock(AssemblyClock):
    def now(self) -> datetime:
        return datetime.now().astimezone()
