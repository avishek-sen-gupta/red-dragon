# pyright: standard
"""Source position of a COBOL construct in the original source file.

Shared by statements, paragraphs and data-division fields. Lines are
1-based and columns 0-based, matching ANTLR's ``getLine()`` and
``getCharPositionInLine()`` — and, deliberately, the tree-sitter
convention used by ``interpreter.ir.SourceLocation``, so the conversion
in ``interpreter/cobol/source_spans.py`` is a straight field mapping.

Note that ``col_end`` is the START column of the construct's last token,
not the end of that token. That is what ANTLR's ``getStop()`` reports and
what the bridge has always emitted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """Source position of a COBOL construct in the original source file."""

    line_start: int
    col_start: int
    line_end: int
    col_end: int

    @classmethod
    def from_dict(cls, data: dict) -> SourceSpan | None:
        """Read a span from a bridge JSON object, or None if it carries no position.

        The bridge omits all four keys together when the underlying ANTLR
        context is absent, so testing one key is sufficient and matches the
        pre-existing per-statement parse blocks this replaces.
        """
        if "line_start" not in data:
            return None
        return cls(
            data["line_start"],
            data["col_start"],
            data["line_end"],
            data["col_end"],
        )

    def write_into(self, result: dict) -> None:
        """Write this span's four flat keys into a bridge JSON object."""
        result["line_start"] = self.line_start
        result["col_start"] = self.col_start
        result["line_end"] = self.line_end
        result["col_end"] = self.col_end
