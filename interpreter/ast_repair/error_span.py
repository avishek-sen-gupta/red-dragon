# pyright: standard
"""ErrorSpan — frozen dataclass representing a contiguous error region in source."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpan:
    """A contiguous region of source that tree-sitter flagged as ERROR or MISSING."""

    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    error_text: str
    context_before: str
    context_after: str
