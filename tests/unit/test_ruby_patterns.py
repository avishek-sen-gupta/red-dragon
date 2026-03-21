"""Unit tests for parse_ruby_pattern — all in-scope pattern types for Ruby case/in.

Diagnostic findings (from ruby_pattern_diag.py):
  - Integer literal  → node type 'integer'
  - String literal   → node type 'string' (with 'string_content' child)
  - Wildcard _       → node type 'identifier' with text '_'
  - Bare identifier  → node type 'identifier'
  - 1 | 2 | 3        → node type 'alternative_pattern'
  - [a, b]           → node type 'array_pattern'
  - Integer => a     → node type 'as_pattern' (constant + '=>' + identifier)
  - *rest            → node type 'splat_parameter'
  - {name: value}    → node type 'hash_pattern' with 'keyword_pattern' children
  - Point[x, y]      → node type 'array_pattern' with leading 'constant'
"""

from __future__ import annotations

import tree_sitter_language_pack as tslp

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    MappingPattern,
    OrPattern,
    SequencePattern,
    StarPattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.ruby import RubyFrontend
from interpreter.frontends.ruby.patterns import parse_ruby_pattern
from interpreter.parser import TreeSitterParserFactory


def _make_ruby_ctx(source: str) -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for Ruby pattern tests."""
    frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
    return TreeSitterEmitContext(
        source=source.encode("utf-8"),
        language=Language.RUBY,
        observer=NullFrontendObserver(),
        constants=frontend._build_constants(),
        type_map=frontend._build_type_map(),
        stmt_dispatch=frontend._build_stmt_dispatch(),
        expr_dispatch=frontend._build_expr_dispatch(),
    )


def _find_all_nodes(node, type_name: str) -> list:
    results = [node] if node.type == type_name else []
    return results + [
        found for child in node.children for found in _find_all_nodes(child, type_name)
    ]


def _parse_pattern_from_case_in(snippet: str, arm_index: int = 0):
    """Parse a Ruby snippet and extract the pattern from the in_clause at arm_index.

    Returns the pattern node (first named child after 'in' keyword that is not 'then').
    """
    parser = tslp.get_parser("ruby")
    tree = parser.parse(snippet.encode("utf-8"))
    in_clauses = _find_all_nodes(tree.root_node, "in_clause")
    clause = in_clauses[arm_index]
    # The pattern is the first named child that isn't the 'then' node
    pattern = next(c for c in clause.children if c.is_named and c.type not in ("then",))
    return pattern


class TestIntegerLiteralPattern:
    def test_integer_literal_maps_to_literal_pattern(self):
        snippet = "case x\n  in 42 then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == LiteralPattern(42)

    def test_integer_zero_maps_to_literal_pattern(self):
        snippet = "case x\n  in 0 then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == LiteralPattern(0)

    def test_negative_integer_maps_to_literal_pattern(self):
        snippet = "case x\n  in -1 then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == LiteralPattern(-1)


class TestStringLiteralPattern:
    def test_string_literal_maps_to_literal_pattern(self):
        snippet = 'case x\n  in "hello" then 1\n  else 0\nend'
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == LiteralPattern("hello")

    def test_empty_string_maps_to_literal_pattern(self):
        snippet = 'case x\n  in "" then 1\n  else 0\nend'
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == LiteralPattern("")


class TestWildcardPattern:
    def test_underscore_maps_to_wildcard_pattern(self):
        snippet = "case x\n  in _ then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == WildcardPattern()

    def test_wildcard_is_not_a_capture(self):
        snippet = "case x\n  in _ then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert not isinstance(result, CapturePattern)


class TestCapturePattern:
    def test_bare_identifier_maps_to_capture_pattern(self):
        snippet = "case x\n  in y then y\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == CapturePattern("y")

    def test_capture_name_is_preserved(self):
        snippet = "case x\n  in value then value\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == CapturePattern("value")


class TestOrPattern:
    def test_two_integer_alternatives(self):
        snippet = "case x\n  in 1 | 2 then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == OrPattern((LiteralPattern(1), LiteralPattern(2)))

    def test_three_integer_alternatives(self):
        snippet = "case x\n  in 1 | 2 | 3 then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert isinstance(result, OrPattern)
        literals = [
            p.value for p in result.alternatives if isinstance(p, LiteralPattern)
        ]
        assert set(literals) == {1, 2, 3}

    def test_string_alternatives(self):
        snippet = 'case x\n  in "a" | "b" then 1\n  else 0\nend'
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert isinstance(result, OrPattern)
        assert LiteralPattern("a") in result.alternatives
        assert LiteralPattern("b") in result.alternatives


class TestArrayPattern:
    def test_two_element_capture_array(self):
        snippet = "case x\n  in [a, b] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == SequencePattern((CapturePattern("a"), CapturePattern("b")))

    def test_array_with_wildcard(self):
        snippet = "case x\n  in [_, b] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == SequencePattern((WildcardPattern(), CapturePattern("b")))

    def test_array_with_literals(self):
        snippet = "case x\n  in [1, 2] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == SequencePattern((LiteralPattern(1), LiteralPattern(2)))

    def test_array_with_splat(self):
        snippet = "case x\n  in [first, *rest] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == SequencePattern((CapturePattern("first"), StarPattern("rest")))

    def test_array_with_anonymous_splat(self):
        snippet = "case x\n  in [first, *] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == SequencePattern((CapturePattern("first"), StarPattern("_")))


class TestAsPattern:
    def test_constant_as_capture(self):
        snippet = "case x\n  in Integer => a then a\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == AsPattern(
            ClassPattern("Integer", positional=(), keyword=()), "a"
        )

    def test_literal_as_capture(self):
        snippet = "case x\n  in 42 => n then n\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == AsPattern(LiteralPattern(42), "n")


class TestHashPattern:
    def test_single_key_capture(self):
        snippet = "case x\n  in {name: n} then n\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == MappingPattern((("name", CapturePattern("n")),))

    def test_two_key_captures(self):
        snippet = "case x\n  in {name: n, age: a} then n\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == MappingPattern(
            (("name", CapturePattern("n")), ("age", CapturePattern("a")))
        )


class TestClassPattern:
    def test_constant_maps_to_class_pattern(self):
        snippet = "case x\n  in Integer then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == ClassPattern("Integer", positional=(), keyword=())

    def test_class_with_positional_args(self):
        snippet = "case x\n  in Point[px, py] then 1\n  else 0\nend"
        ctx = _make_ruby_ctx(snippet)
        pattern = _parse_pattern_from_case_in(snippet, arm_index=0)
        result = parse_ruby_pattern(ctx, pattern)
        assert result == ClassPattern(
            "Point",
            positional=(CapturePattern("px"), CapturePattern("py")),
            keyword=(),
        )
