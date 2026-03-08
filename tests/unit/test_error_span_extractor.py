"""Tests for interpreter.ast_repair.error_span_extractor."""

from __future__ import annotations

import tree_sitter_language_pack as tslp

from interpreter.ast_repair.error_span_extractor import extract


class TestExtractNoErrors:
    def test_valid_python_returns_empty(self):
        parser = tslp.get_parser("python")
        source = b"x = 1\nprint(x)\n"
        tree = parser.parse(source)
        assert extract(tree.root_node, source) == []


class TestExtractDetectsErrors:
    def test_malformed_python_detects_error(self):
        parser = tslp.get_parser("python")
        source = b"def foo(:\n  return 1\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source)
        assert len(spans) >= 1
        assert spans[0].start_line == 0

    def test_missing_closing_paren(self):
        parser = tslp.get_parser("python")
        source = b"print(1\nx = 2\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source)
        assert len(spans) >= 1


class TestLineExpansion:
    def test_error_at_mid_line_expands_to_full_line(self):
        parser = tslp.get_parser("python")
        # The error is mid-line but the span should cover the full line
        source = b"x = 1\ndef foo(:\n  return 1\ny = 2\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source)
        assert len(spans) >= 1
        # The error region should include the full line(s) where the error occurs
        error_lines = set()
        for span in spans:
            error_lines.update(range(span.start_line, span.end_line + 1))
        # Line 1 (def foo(:) should be in the error region
        assert 1 in error_lines


class TestMergeOverlapping:
    def test_adjacent_errors_merged(self):
        parser = tslp.get_parser("python")
        # Two consecutive bad lines — should merge into one span
        source = b"def foo(:\ndef bar(:\nx = 1\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source)
        # Adjacent error lines merge into a single span covering both
        assert len(spans) == 1
        assert spans[0].start_line == 0
        assert spans[0].end_line == 1


class TestContextLines:
    def test_context_lines_extracted(self):
        parser = tslp.get_parser("python")
        source = b"a = 1\nb = 2\nc = 3\ndef foo(:\ne = 5\nf = 6\ng = 7\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source, context_lines=2)
        assert len(spans) >= 1
        # There should be some context before and/or after the error
        first = spans[0]
        # Context before should include lines before the error
        if first.start_line >= 2:
            assert first.context_before != ""

    def test_context_at_start_of_file(self):
        parser = tslp.get_parser("python")
        source = b"def foo(:\nx = 1\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source, context_lines=3)
        assert len(spans) >= 1
        # Context before at start of file should be empty string
        assert spans[0].context_before == ""

    def test_zero_context_lines(self):
        parser = tslp.get_parser("python")
        source = b"a = 1\ndef foo(:\nc = 3\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source, context_lines=0)
        assert len(spans) >= 1
        first = spans[0]
        assert first.context_before == ""
        assert first.context_after == ""


class TestErrorText:
    def test_error_text_contains_broken_source(self):
        parser = tslp.get_parser("python")
        source = b"x = 1\ndef foo(:\n  return 1\ny = 2\n"
        tree = parser.parse(source)
        spans = extract(tree.root_node, source)
        assert len(spans) >= 1
        # The error text should contain the malformed def line
        combined_error_text = " ".join(s.error_text for s in spans)
        assert "def" in combined_error_text or "foo" in combined_error_text
