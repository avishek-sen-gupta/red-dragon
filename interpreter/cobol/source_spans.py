# pyright: standard
"""Conversion from the COBOL ASG's SourceSpan to the IR's SourceLocation.

This lives on the interpreter side on purpose: ``cobol_asg`` imports
nothing from ``interpreter`` and that one-way dependency is enforced by
import-linter. The ASG never learns about IR types.

The two types agree on convention — 1-based lines, 0-based columns — but
transpose their field names (``line_start`` vs ``start_line``), which is
the only thing this module exists to get right.
"""

from __future__ import annotations

from cobol_asg.source_span import SourceSpan
from interpreter.ir import NO_SOURCE_LOCATION, SourceLocation


def to_source_location(span: SourceSpan | None) -> SourceLocation:
    """Convert a COBOL span to an IR source location.

    A ``None`` span becomes ``NO_SOURCE_LOCATION`` rather than raising:
    plenty of emitted instructions (the program prologue, compiler-
    allocated index items) legitimately correspond to no source text.
    """
    if span is None:
        return NO_SOURCE_LOCATION
    return SourceLocation(
        start_line=span.line_start,
        start_col=span.col_start,
        end_line=span.line_end,
        end_col=span.col_end,
    )
