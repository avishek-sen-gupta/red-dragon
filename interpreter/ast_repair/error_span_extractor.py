# pyright: standard
"""Pure functions to extract ErrorSpan regions from a tree-sitter AST."""

from __future__ import annotations

import logging
from functools import reduce
from typing import Any

from interpreter.ast_repair.error_span import ErrorSpan

logger = logging.getLogger(__name__)


def extract(root_node: Any, source: bytes, context_lines: int = 3) -> list[ErrorSpan]:
    """Walk a tree-sitter AST and collect error/missing spans.

    Fast-path: returns empty list immediately when ``root_node.has_error`` is False.
    """
    if not root_node.has_error:
        return []

    raw_spans = _collect_error_nodes(root_node)
    if not raw_spans:
        return []

    lines = source.split(b"\n")
    line_expanded = [_expand_to_lines(span, lines) for span in raw_spans]
    merged = _merge_overlapping(line_expanded)
    return [_attach_context(span, lines, context_lines) for span in merged]


def _is_error_node(node: Any) -> bool:
    """Check whether a tree-sitter node represents a parse error or missing token."""
    return node.is_error or node.is_missing


def _collect_error_nodes(node: Any) -> list[ErrorSpan]:
    """Recursively collect ERROR/MISSING nodes from the AST."""
    if _is_error_node(node):
        return [
            ErrorSpan(
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                error_text="",
                context_before="",
                context_after="",
            )
        ]
    return reduce(
        lambda acc, child: acc + _collect_error_nodes(child),
        node.children,
        [],
    )


def _expand_to_lines(span: ErrorSpan, lines: list[bytes]) -> ErrorSpan:
    """Expand byte offsets to cover full lines."""
    start_byte = sum(len(line) + 1 for line in lines[: span.start_line])
    end_line = min(span.end_line, len(lines) - 1)
    end_byte = sum(len(line) + 1 for line in lines[: end_line + 1])
    error_text = b"\n".join(lines[span.start_line : end_line + 1]).decode(
        "utf-8", errors="replace"
    )
    return ErrorSpan(
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=span.start_line,
        end_line=end_line,
        error_text=error_text,
        context_before="",
        context_after="",
    )


def _merge_overlapping(spans: list[ErrorSpan]) -> list[ErrorSpan]:
    """Merge overlapping or adjacent expanded spans."""
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: s.start_line)
    merged: list[ErrorSpan] = [sorted_spans[0]]
    for span in sorted_spans[1:]:
        prev = merged[-1]
        if span.start_line <= prev.end_line + 1:
            combined_text = (
                prev.error_text + "\n" + span.error_text
                if span.start_line > prev.end_line
                else prev.error_text
            )
            merged[-1] = ErrorSpan(
                start_byte=prev.start_byte,
                end_byte=max(prev.end_byte, span.end_byte),
                start_line=prev.start_line,
                end_line=max(prev.end_line, span.end_line),
                error_text=combined_text,
                context_before="",
                context_after="",
            )
        else:
            merged.append(span)
    return merged


def _attach_context(
    span: ErrorSpan, lines: list[bytes], context_lines: int
) -> ErrorSpan:
    """Attach N lines of context before/after the span."""
    ctx_start = max(0, span.start_line - context_lines)
    ctx_end = min(len(lines), span.end_line + 1 + context_lines)
    context_before = b"\n".join(lines[ctx_start : span.start_line]).decode(
        "utf-8", errors="replace"
    )
    context_after = b"\n".join(lines[span.end_line + 1 : ctx_end]).decode(
        "utf-8", errors="replace"
    )
    return ErrorSpan(
        start_byte=span.start_byte,
        end_byte=span.end_byte,
        start_line=span.start_line,
        end_line=span.end_line,
        error_text=span.error_text,
        context_before=context_before,
        context_after=context_after,
    )
