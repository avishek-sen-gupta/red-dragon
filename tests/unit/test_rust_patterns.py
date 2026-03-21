"""Unit tests for parse_rust_pattern — Literals, Wildcards, Captures."""

from __future__ import annotations

import tree_sitter_language_pack as tslp

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.common.patterns import (
    CapturePattern,
    ClassPattern,
    DerefPattern,
    LiteralPattern,
    OrPattern,
    SequencePattern,
    ValuePattern,
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


class TestReferencePattern:
    def test_ref_capture(self):
        """&val in match should produce DerefPattern(CapturePattern('val'))."""
        snippet = "fn main() { match r { &val => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == DerefPattern(CapturePattern("val"))

    def test_ref_literal(self):
        """&42 in match should produce DerefPattern(LiteralPattern(42))."""
        snippet = "fn main() { match r { &42 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == DerefPattern(LiteralPattern(42))

    def test_ref_wildcard(self):
        """&_ in match should produce DerefPattern(WildcardPattern())."""
        snippet = "fn main() { match r { &_ => 1, } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == DerefPattern(WildcardPattern())


class TestOrPattern:
    def test_or_pattern_three_literals(self):
        snippet = "fn main() { match x { 1 | 2 | 3 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == OrPattern(
            (LiteralPattern(1), LiteralPattern(2), LiteralPattern(3))
        )

    def test_or_pattern_two_literals(self):
        snippet = "fn main() { match x { 0 | 1 => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == OrPattern((LiteralPattern(0), LiteralPattern(1)))


class TestTuplePattern:
    def test_tuple_two_captures(self):
        snippet = "fn main() { match p { (x, y) => x + y, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == SequencePattern((CapturePattern("x"), CapturePattern("y")))

    def test_tuple_with_wildcard(self):
        snippet = "fn main() { match p { (_, y) => y, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == SequencePattern((WildcardPattern(), CapturePattern("y")))

    def test_tuple_with_literal(self):
        snippet = "fn main() { match p { (0, y) => y, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == SequencePattern((LiteralPattern(0), CapturePattern("y")))


class TestTupleStructPattern:
    def test_some_with_capture(self):
        snippet = "fn main() { match v { Some(x) => x, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Option", positional=(CapturePattern("x"),), keyword=()
        )

    def test_some_with_wildcard(self):
        snippet = "fn main() { match v { Some(_) => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Option", positional=(WildcardPattern(),), keyword=()
        )

    def test_some_with_tuple_inner(self):
        snippet = "fn main() { match v { Some((a, b)) => a, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Option",
            positional=(SequencePattern((CapturePattern("a"), CapturePattern("b"))),),
            keyword=(),
        )

    def test_nested_some_some(self):
        snippet = "fn main() { match v { Some(Some(x)) => x, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Option",
            positional=(
                ClassPattern("Option", positional=(CapturePattern("x"),), keyword=()),
            ),
            keyword=(),
        )


class TestStructPattern:
    def test_point_shorthand_fields(self):
        snippet = "fn main() { match p { Point { x, y } => x + y, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Point",
            positional=(),
            keyword=(("x", CapturePattern("x")), ("y", CapturePattern("y"))),
        )

    def test_struct_explicit_field(self):
        snippet = "fn main() { match p { Point { x: a, y: b } => a + b, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Point",
            positional=(),
            keyword=(("x", CapturePattern("a")), ("y", CapturePattern("b"))),
        )

    def test_struct_single_shorthand_field(self):
        snippet = "fn main() { match s { Foo { val } => val, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ClassPattern(
            "Foo",
            positional=(),
            keyword=(("val", CapturePattern("val")),),
        )


class TestScopedIdentifierPattern:
    def test_scoped_identifier_maps_to_value_pattern(self):
        snippet = "fn main() { match c { Color::Red => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ValuePattern(("Color", "Red"))

    def test_scoped_identifier_preserves_parts(self):
        snippet = "fn main() { match s { Shape::Circle => 1, _ => 0 } }"
        ctx = _make_rust_ctx(snippet)
        _, inner = _parse_pattern_from_snippet(snippet, arm_index=0)
        result = parse_rust_pattern(ctx, inner)
        assert result == ValuePattern(("Shape", "Circle"))
