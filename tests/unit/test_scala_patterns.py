"""Unit tests for parse_scala_pattern — Literals, Wildcards, Captures."""

from __future__ import annotations

import tree_sitter_language_pack as tslp

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.common.patterns import (
    CapturePattern,
    LiteralPattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.scala import ScalaFrontend
from interpreter.frontends.scala.patterns import parse_scala_pattern
from interpreter.parser import TreeSitterParserFactory


def _make_scala_ctx(source: str) -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for Scala pattern tests."""
    frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
    return TreeSitterEmitContext(
        source=source.encode("utf-8"),
        language=Language.SCALA,
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


def _parse_pattern_from_snippet(snippet: str, arm_index: int = 0):
    """Parse a Scala snippet, extract the pattern from the given case clause index."""
    parser = tslp.get_parser("scala")
    tree = parser.parse(snippet.encode("utf-8"))
    clauses = _find_all_nodes(tree.root_node, "case_clause")
    clause = clauses[arm_index]
    pattern = clause.child_by_field_name("pattern")
    return pattern


class TestIntegerLiteralPattern:
    def test_integer_literal_maps_to_literal_pattern(self):
        snippet = "object M { def f(x: Any) = x match { case 42 => 1; case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(42)

    def test_integer_literal_zero(self):
        snippet = "object M { def f(x: Any) = x match { case 0 => 1; case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(0)

    def test_integer_literal_with_underscore_separator(self):
        snippet = (
            "object M { def f(x: Any) = x match { case 1_000 => 1; case _ => 0 } }"
        )
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(1000)


class TestFloatLiteralPattern:
    def test_float_literal_maps_to_literal_pattern(self):
        snippet = "object M { def f(x: Any) = x match { case 3.14 => 1; case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(3.14)


class TestStringLiteralPattern:
    def test_string_literal_maps_to_literal_pattern(self):
        snippet = (
            'object M { def f(x: Any) = x match { case "hello" => 1; case _ => 0 } }'
        )
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern("hello")

    def test_empty_string_literal(self):
        snippet = 'object M { def f(x: Any) = x match { case "" => 1; case _ => 0 } }'
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern("")


class TestBooleanLiteralPattern:
    def test_true_maps_to_literal_true(self):
        snippet = "object M { def f(x: Any) = x match { case true => 1; case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(True)

    def test_false_maps_to_literal_false(self):
        snippet = (
            "object M { def f(x: Any) = x match { case false => 1; case _ => 0 } }"
        )
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == LiteralPattern(False)


class TestWildcardPattern:
    def test_wildcard_maps_to_wildcard_pattern(self):
        snippet = "object M { def f(x: Any) = x match { case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == WildcardPattern()

    def test_wildcard_is_not_a_capture(self):
        snippet = "object M { def f(x: Any) = x match { case _ => 0 } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert not isinstance(result, CapturePattern)


class TestCapturePattern:
    def test_bare_identifier_maps_to_capture_pattern(self):
        snippet = "object M { def f(x: Any) = x match { case y => y } }"
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == CapturePattern("y")

    def test_capture_name_is_preserved(self):
        snippet = (
            "object M { def f(x: Any) = x match { case value => value; case _ => 0 } }"
        )
        ctx = _make_scala_ctx(snippet)
        pattern = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_scala_pattern(ctx, pattern)
        assert result == CapturePattern("value")
