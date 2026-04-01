# pyright: standard
"""Pure function to apply repaired fragments to source bytes."""

from __future__ import annotations

from interpreter.ast_repair.error_span import ErrorSpan


def patch(
    source: bytes, error_spans: list[ErrorSpan], repaired_fragments: list[str]
) -> bytes:
    """Replace error spans in *source* with *repaired_fragments*.

    Applies patches from end-of-file backward so earlier byte offsets stay valid.
    """
    pairs = sorted(
        zip(error_spans, repaired_fragments),
        key=lambda p: p[0].start_byte,
        reverse=True,
    )
    result = source
    for span, fragment in pairs:
        result = (
            result[: span.start_byte]
            + fragment.encode("utf-8")
            + result[span.end_byte :]
        )
    return result
