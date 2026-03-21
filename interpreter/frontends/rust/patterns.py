"""Parse tree-sitter Rust pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    OrPattern,
    Pattern,
    SequencePattern,
    ValuePattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.rust.node_types import RustNodeType

# Rust enum variant → canonical class name mapping
_VARIANT_TO_CLASS: dict[str, str] = {
    "Some": "Option",
    "Ok": "Result",
    "Err": "Result",
}

_WILDCARD_TEXT = "_"


def parse_rust_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Rust pattern node to the Pattern ADT.

    Handles: integer literals, float literals, string literals, boolean
    literals, negative literals, wildcards, and bare identifier captures.
    """
    text = ctx.node_text(node)

    # Wildcard: tree-sitter emits _ as an anonymous node; check text first
    if text == _WILDCARD_TEXT:
        return WildcardPattern()

    node_type = node.type

    if node_type in (RustNodeType.INTEGER_LITERAL, RustNodeType.FLOAT_LITERAL):
        return LiteralPattern(_parse_number(text))

    if node_type == RustNodeType.STRING_LITERAL:
        content_nodes = [
            c for c in node.children if c.type == RustNodeType.STRING_CONTENT
        ]
        content = ctx.node_text(content_nodes[0]) if content_nodes else ""
        return LiteralPattern(content)

    if node_type == RustNodeType.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    if node_type == RustNodeType.NEGATIVE_LITERAL:
        # Children: '-' (anon) then the numeric literal (named)
        numeric_node = next(c for c in node.children if c.is_named)
        return LiteralPattern(-_parse_number(ctx.node_text(numeric_node)))

    if node_type == RustNodeType.IDENTIFIER:
        return CapturePattern(text)

    if node_type == RustNodeType.OR_PATTERN:
        return OrPattern(tuple(_flatten_or_pattern(ctx, node)))

    if node_type == RustNodeType.TUPLE_PATTERN:
        elements = tuple(
            parse_rust_pattern(ctx, c)
            for c in node.children
            if c.is_named or ctx.node_text(c) == _WILDCARD_TEXT
        )
        return SequencePattern(elements)

    if node_type == RustNodeType.SCOPED_IDENTIFIER:
        parts = tuple(text.split("::"))
        return ValuePattern(parts)

    if node_type == RustNodeType.TUPLE_STRUCT_PATTERN:
        return _parse_tuple_struct_pattern(ctx, node)

    if node_type == RustNodeType.STRUCT_PATTERN:
        return _parse_struct_pattern(ctx, node)

    raise ValueError(f"Unsupported Rust pattern node type: {node_type!r} ({text!r})")


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float, stripping _ separators."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)


def _parse_tuple_struct_pattern(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse a tuple_struct_pattern node: Some(x), Message::Write(text)."""
    name_node = next(
        c
        for c in node.children
        if c.type in (RustNodeType.IDENTIFIER, RustNodeType.SCOPED_IDENTIFIER)
    )
    raw_name = ctx.node_text(name_node)
    class_name = _VARIANT_TO_CLASS.get(raw_name, raw_name)
    positional = tuple(
        parse_rust_pattern(ctx, c)
        for c in node.children
        if (c.is_named or ctx.node_text(c) == _WILDCARD_TEXT) and c != name_node
    )
    return ClassPattern(class_name, positional=positional, keyword=())


def _parse_struct_pattern(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse a struct_pattern node: Point { x, y }."""
    type_node = next(
        c
        for c in node.children
        if c.type in (RustNodeType.TYPE_IDENTIFIER, RustNodeType.SCOPED_TYPE_IDENTIFIER)
    )
    class_name = ctx.node_text(type_node)
    field_patterns = [c for c in node.children if c.type == RustNodeType.FIELD_PATTERN]
    keyword = tuple(_parse_field_pattern(ctx, fp) for fp in field_patterns)
    return ClassPattern(class_name, positional=(), keyword=keyword)


def _parse_field_pattern(ctx: TreeSitterEmitContext, fp) -> tuple[str, Pattern]:
    """Parse a single field_pattern into a (name, Pattern) pair."""
    # Shorthand: Point { x } — shorthand_field_identifier is both name and capture
    shorthand = next(
        (c for c in fp.children if c.type == RustNodeType.SHORTHAND_FIELD_IDENTIFIER),
        None,
    )
    if shorthand:
        name = ctx.node_text(shorthand)
        return (name, CapturePattern(name))
    # Explicit: Point { x: val }
    field_name_node = next(
        c for c in fp.children if c.type == RustNodeType.FIELD_IDENTIFIER
    )
    pattern_child = next(c for c in fp.children if c.is_named and c != field_name_node)
    return (ctx.node_text(field_name_node), parse_rust_pattern(ctx, pattern_child))


def _flatten_or_pattern(ctx: TreeSitterEmitContext, node) -> list[Pattern]:
    """Flatten a left-associative or_pattern tree into a flat list of alternatives.

    Tree-sitter parses `1 | 2 | 3` as `or_pattern(or_pattern(1, 2), 3)`.
    This function recursively flattens nested or_pattern nodes.
    """
    named = [c for c in node.children if c.is_named]
    return [
        leaf
        for c in named
        for leaf in (
            _flatten_or_pattern(ctx, c)
            if c.type == RustNodeType.OR_PATTERN
            else [parse_rust_pattern(ctx, c)]
        )
    ]
