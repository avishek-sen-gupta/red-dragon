# pyright: standard
"""A system variable whose value the assembly is given, keyed by the bridge option that carries it."""

from __future__ import annotations

from enum import Enum


class AssemblyInput(Enum):
    SYSPARM = "--sysparm"
    SYSJOB = "--sysjob"
    SYSSTEP = "--sysstep"
    SYSIN_DSN = "--sysin-dsn"
    SYSIN_MEMBER = "--sysin-member"
