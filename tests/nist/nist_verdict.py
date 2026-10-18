"""The pytest verdict a NIST program's test reaches: pass, fail or skip."""

from __future__ import annotations

from enum import Enum


class NistVerdict(Enum):
    """The pytest verdict a NIST program's test reaches."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
