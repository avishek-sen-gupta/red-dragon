"""FUNCTION WHEN-COMPILED's 21-character rendering of a compile stamp."""

from __future__ import annotations

from datetime import datetime


def when_compiled_text(compiled_at: datetime) -> str:
    return (
        compiled_at.strftime("%Y%m%d%H%M%S")
        + f"{compiled_at.microsecond // 10000:02d}"
        + compiled_at.strftime("%z")
    )
