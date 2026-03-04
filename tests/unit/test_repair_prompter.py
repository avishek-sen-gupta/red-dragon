"""Tests for interpreter.ast_repair.repair_prompter."""

from __future__ import annotations

from interpreter.ast_repair.error_span import ErrorSpan
from interpreter.ast_repair.repair_prompter import (
    FRAGMENT_DELIMITER,
    build_prompt,
    parse_response,
)


def _span(
    error_text: str, context_before: str = "", context_after: str = ""
) -> ErrorSpan:
    return ErrorSpan(
        start_byte=0,
        end_byte=0,
        start_line=0,
        end_line=0,
        error_text=error_text,
        context_before=context_before,
        context_after=context_after,
    )


class TestBuildPrompt:
    def test_single_span_prompt(self):
        spans = [_span("def foo(:", context_before="x = 1", context_after="y = 2")]
        prompt = build_prompt("python", spans)
        assert "python" in prompt.system_prompt
        assert "syntax" in prompt.system_prompt.lower()
        assert "def foo(:" in prompt.user_prompt
        assert "x = 1" in prompt.user_prompt
        assert "y = 2" in prompt.user_prompt

    def test_multi_span_prompt_has_delimiter(self):
        spans = [_span("bad1"), _span("bad2")]
        prompt = build_prompt("javascript", spans)
        assert FRAGMENT_DELIMITER in prompt.user_prompt
        assert "bad1" in prompt.user_prompt
        assert "bad2" in prompt.user_prompt

    def test_no_context_omits_context_sections(self):
        spans = [_span("broken code")]
        prompt = build_prompt("python", spans)
        assert "Context before" not in prompt.user_prompt
        assert "Context after" not in prompt.user_prompt

    def test_language_in_system_prompt(self):
        prompt = build_prompt("rust", [_span("x")])
        assert "rust" in prompt.system_prompt


class TestParseResponse:
    def test_single_fragment(self):
        result = parse_response("def foo():", 1)
        assert result == ["def foo():"]

    def test_multi_fragment(self):
        response = f"def foo():\n{FRAGMENT_DELIMITER}\nlet x = 1;"
        result = parse_response(response, 2)
        assert result == ["def foo():", "let x = 1;"]

    def test_too_many_fragments_truncates(self):
        response = f"a\n{FRAGMENT_DELIMITER}\nb\n{FRAGMENT_DELIMITER}\nc"
        result = parse_response(response, 2)
        assert result == ["a", "b"]

    def test_too_few_fragments_pads(self):
        result = parse_response("only one", 3)
        assert len(result) == 3
        assert result[0] == "only one"
        assert result[1] == ""
        assert result[2] == ""

    def test_empty_response_pads(self):
        result = parse_response("", 2)
        assert result == ["", ""]

    def test_strips_whitespace(self):
        response = f"  def foo():  \n{FRAGMENT_DELIMITER}\n  let x = 1;  "
        result = parse_response(response, 2)
        assert result == ["def foo():", "let x = 1;"]
