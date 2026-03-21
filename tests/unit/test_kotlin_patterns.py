"""Unit tests for parse_kotlin_pattern — TDD first, then implementation.

Tree-sitter structure for Kotlin when conditions:
  when_condition
    <pattern_node>      <- first named child

For is-type checks:
  when_condition
    type_test
      is              (anonymous)
      user_type
        type_identifier  (named)

For string literals:
  string_literal
    string_content    (named)
"""

from __future__ import annotations

import tree_sitter_language_pack as tslp

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.common.patterns import (
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.kotlin.patterns import parse_kotlin_pattern
from interpreter.parser import TreeSitterParserFactory


def _make_kotlin_ctx(source: str) -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for Kotlin pattern tests."""
    frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
    return TreeSitterEmitContext(
        source=source.encode("utf-8"),
        language=Language.KOTLIN,
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


def _parse_pattern_from_snippet(snippet: str, entry_index: int = 0):
    """Parse a Kotlin snippet, extract the inner pattern node from a when_entry.

    Returns the first named child of the when_condition, which is the actual
    pattern node (integer_literal, type_test, simple_identifier, etc.).
    """
    parser = tslp.get_parser("kotlin")
    tree = parser.parse(snippet.encode("utf-8"))
    entries = _find_all_nodes(tree.root_node, "when_entry")
    entry = entries[entry_index]
    conditions = _find_all_nodes(entry, "when_condition")
    # when_condition's first named child is the pattern node
    cond = conditions[0]
    return next(c for c in cond.children if c.is_named)


class TestIntegerLiteralPattern:
    def test_integer_literal_maps_to_literal_pattern(self):
        snippet = "fun test(x: Any) { when (x) { 42 -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(42)

    def test_integer_literal_zero(self):
        snippet = "fun test(x: Any) { when (x) { 0 -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(0)

    def test_integer_literal_with_underscore_separator(self):
        snippet = "fun test(x: Any) { when (x) { 1_000 -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(1000)


class TestRealLiteralPattern:
    def test_real_literal_maps_to_literal_pattern(self):
        snippet = "fun test(x: Any) { when (x) { 3.14 -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(3.14)

    def test_real_literal_with_f_suffix(self):
        snippet = "fun test(x: Any) { when (x) { 2.5f -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(2.5)


class TestStringLiteralPattern:
    def test_string_literal_maps_to_literal_pattern(self):
        snippet = 'fun test(x: Any) { when (x) { "hello" -> 1; else -> 0 } }'
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern("hello")

    def test_empty_string_literal(self):
        snippet = 'fun test(x: Any) { when (x) { "" -> 1; else -> 0 } }'
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern("")


class TestBooleanLiteralPattern:
    def test_true_maps_to_literal_true(self):
        snippet = "fun test(x: Any) { when (x) { true -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(True)

    def test_false_maps_to_literal_false(self):
        snippet = "fun test(x: Any) { when (x) { false -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(False)


class TestNullLiteralPattern:
    def test_null_maps_to_literal_none(self):
        snippet = "fun test(x: Any?) { when (x) { null -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == LiteralPattern(None)


class TestCapturePattern:
    def test_simple_identifier_maps_to_capture_pattern(self):
        # In Kotlin when without subject, a bare identifier in an entry is a capture
        snippet = "fun test(x: Int) { when (x) { 1 -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        # We test by constructing the node directly: parse a snippet that gives
        # a simple_identifier as the when_condition's first named child.
        # This happens in `when` entries where a variable-bound check would occur.
        # For the purpose of testing parse_kotlin_pattern, we pass a simple_identifier.
        parser = tslp.get_parser("kotlin")
        # Use a snippet that has a simple_identifier directly as the condition
        capture_snippet = (
            "fun test(x: Int) { val y = 1; when (x) { y -> 1; else -> 0 } }"
        )
        src = capture_snippet.encode("utf-8")
        tree = parser.parse(src)
        entries = _find_all_nodes(tree.root_node, "when_entry")
        cond_node = _find_all_nodes(entries[0], "when_condition")[0]
        inner = next(c for c in cond_node.children if c.is_named)
        capture_ctx = _make_kotlin_ctx(capture_snippet)
        result = parse_kotlin_pattern(capture_ctx, inner)
        assert result == CapturePattern("y")

    def test_capture_name_preserved(self):
        capture_snippet = (
            "fun test(x: Int) { val value = 5; when (x) { value -> 1; else -> 0 } }"
        )
        parser = tslp.get_parser("kotlin")
        src = capture_snippet.encode("utf-8")
        tree = parser.parse(src)
        entries = _find_all_nodes(tree.root_node, "when_entry")
        cond_node = _find_all_nodes(entries[0], "when_condition")[0]
        inner = next(c for c in cond_node.children if c.is_named)
        ctx = _make_kotlin_ctx(capture_snippet)
        result = parse_kotlin_pattern(ctx, inner)
        assert result == CapturePattern("value")


class TestIsTypePattern:
    def test_is_int_maps_to_class_pattern(self):
        """Diagnostic: verify tree-sitter emits type_test for `is Int`."""
        snippet = "fun test(x: Any) { when (x) { is Int -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        # The node should be type_test
        assert node.type == "type_test", (
            f"Expected type_test but got {node.type!r}. "
            f"Tree-sitter node structure diagnostic."
        )
        result = parse_kotlin_pattern(ctx, node)
        assert result == ClassPattern("Int", positional=(), keyword=())

    def test_is_string_maps_to_class_pattern(self):
        snippet = "fun test(x: Any) { when (x) { is String -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert result == ClassPattern("String", positional=(), keyword=())

    def test_is_type_has_empty_positional_and_keyword(self):
        snippet = "fun test(x: Any) { when (x) { is Double -> 1; else -> 0 } }"
        ctx = _make_kotlin_ctx(snippet)
        node = _parse_pattern_from_snippet(snippet, entry_index=0)
        result = parse_kotlin_pattern(ctx, node)
        assert isinstance(result, ClassPattern)
        assert result.positional == ()
        assert result.keyword == ()

    def test_multiple_is_type_entries(self):
        """Verify correct class name extraction for multiple is-type entries."""
        snippet = (
            "fun test(x: Any) { when (x) { is Int -> 1; is String -> 2; else -> 0 } }"
        )
        ctx = _make_kotlin_ctx(snippet)
        int_node = _parse_pattern_from_snippet(snippet, entry_index=0)
        str_node = _parse_pattern_from_snippet(snippet, entry_index=1)
        int_result = parse_kotlin_pattern(ctx, int_node)
        str_result = parse_kotlin_pattern(ctx, str_node)
        assert int_result == ClassPattern("Int", positional=(), keyword=())
        assert str_result == ClassPattern("String", positional=(), keyword=())
