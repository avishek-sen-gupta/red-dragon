"""Tests for interpreter.ast_repair.source_patcher."""

from __future__ import annotations

from interpreter.ast_repair.error_span import ErrorSpan
from interpreter.ast_repair.source_patcher import patch


def _span(start_byte: int, end_byte: int) -> ErrorSpan:
    """Helper to build a minimal ErrorSpan with only byte offsets."""
    return ErrorSpan(
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=0,
        end_line=0,
        error_text="",
        context_before="",
        context_after="",
    )


class TestPatchSingleSpan:
    def test_replace_middle(self):
        source = b"aaaBBBccc"
        spans = [_span(3, 6)]
        result = patch(source, spans, ["XXX"])
        assert result == b"aaaXXXccc"

    def test_replace_with_shorter(self):
        source = b"aaaBBBccc"
        spans = [_span(3, 6)]
        result = patch(source, spans, ["X"])
        assert result == b"aaaXccc"

    def test_replace_with_longer(self):
        source = b"aaaBBBccc"
        spans = [_span(3, 6)]
        result = patch(source, spans, ["XXXXX"])
        assert result == b"aaaXXXXXccc"


class TestPatchMultipleSpans:
    def test_two_disjoint_spans(self):
        source = b"aaaBBBcccDDDeee"
        spans = [_span(3, 6), _span(9, 12)]
        result = patch(source, spans, ["XX", "YY"])
        assert result == b"aaaXXcccYYeee"

    def test_offsets_stay_valid_with_different_lengths(self):
        source = b"aaaBcccDDeee"
        # First span at byte 3-4 (1 byte), second at 7-9 (2 bytes)
        spans = [_span(3, 4), _span(7, 9)]
        result = patch(source, spans, ["XXXXX", "Y"])
        assert result == b"aaaXXXXXcccYeee"


class TestPatchEdgeCases:
    def test_empty_spans_returns_unchanged(self):
        source = b"hello world"
        assert patch(source, [], []) == source

    def test_replace_at_start(self):
        source = b"BBBccc"
        result = patch(source, [_span(0, 3)], ["AA"])
        assert result == b"AAccc"

    def test_replace_at_end(self):
        source = b"aaaBBB"
        result = patch(source, [_span(3, 6)], ["CC"])
        assert result == b"aaaCC"
