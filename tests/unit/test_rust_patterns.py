"""Unit tests for parse_rust_pattern — Literals, Wildcards, Captures."""

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
from interpreter.frontends.rust import RustFrontend
from interpreter.frontends.rust.patterns import parse_rust_pattern
from interpreter.parser import TreeSitterParserFactory


def _make_rust_ctx(source: str) -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for Rust pattern tests."""
    frontend = RustFrontend(TreeSitterParserFactory(), "rust")
    ctx = TreeSitterEmitContext(
        source=source.encode("utf-8"),
        language=Language.RUST,
        observer=NullFrontendObserver(),
        constants=frontend._build_constants(),
        type_map=frontend._build_type_map(),
        stmt_dispatch=frontend._build_stmt_dispatch(),
        expr_dispatch=frontend._build_expr_dispatch(),
    )
    return ctx


def _parse_pattern_from_snippet(snippet: str, arm_index: int = 0):
    """
    Parse a Rust snippet, extract the pattern from the given match arm index,
    and return the inner pattern node (unwrapped from match_pattern).
    """
    parser = tslp.get_parser("rust")
    tree = parser.parse(snippet.encode("utf-8"))
    arms = _find_all_nodes(tree.root_node, "match_arm")
    arm = arms[arm_index]
    match_pattern = next(c for c in arm.children if c.type == "match_pattern")
    # Unwrap match_pattern to its inner child (named or anonymous)
    named_children = [c for c in match_pattern.children if c.is_named]
    if named_children:
        return match_pattern, named_children[0]
    # Wildcard: anonymous _ child
    anon_children = [c for c in match_pattern.children if not c.is_named]
    return match_pattern, anon_children[0]


def _find_all_nodes(node, type_name: str) -> list:
    results = [node] if node.type == type_name else []
    return results + [
        found for child in node.children for found in _find_all_nodes(child, type_name)
    ]


class TestIntegerLiteralPattern:
    def test_integer_literal_maps_to_literal_pattern(self):
        snippet = "fn main() { match x { 42 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(42)

    def test_integer_literal_zero(self):
        snippet = "fn main() { match x { 0 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(0)

    def test_integer_literal_with_underscore_separator(self):
        snippet = "fn main() { match x { 1_000 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(1000)


class TestFloatLiteralPattern:
    def test_float_literal_maps_to_literal_pattern(self):
        snippet = "fn main() { match x { 3.14 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(3.14)


class TestStringLiteralPattern:
    def test_string_literal_maps_to_literal_pattern(self):
        snippet = 'fn main() { match x { "hello" => 1, _ => 0 } }'
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern("hello")

    def test_empty_string_literal(self):
        snippet = 'fn main() { match x { "" => 1, _ => 0 } }'
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern("")


class TestBooleanLiteralPattern:
    def test_true_maps_to_literal_true(self):
        snippet = "fn main() { match x { true => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(True)

    def test_false_maps_to_literal_false(self):
        snippet = "fn main() { match x { false => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(False)


class TestNegativeLiteralPattern:
    def test_negative_integer_maps_to_literal_pattern(self):
        snippet = "fn main() { match x { -1 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(-1)

    def test_negative_float_maps_to_literal_pattern(self):
        snippet = "fn main() { match x { -3.14 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == LiteralPattern(-3.14)


class TestWildcardPattern:
    def test_wildcard_underscore_maps_to_wildcard_pattern(self):
        snippet = "fn main() { match x { _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == WildcardPattern()

    def test_wildcard_is_not_a_capture(self):
        snippet = "fn main() { match x { _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert not isinstance(result, CapturePattern)


class TestCapturePattern:
    def test_bare_identifier_maps_to_capture_pattern(self):
        snippet = "fn main() { match x { y => y + 1 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == CapturePattern("y")

    def test_capture_name_is_preserved(self):
        snippet = "fn main() { match x { value => value, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == CapturePattern("value")
