"""Parse tree-sitter Rust pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    LiteralPattern,
    OrPattern,
    Pattern,
    SequencePattern,
    ValuePattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.rust.node_types import RustNodeType

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
        content_nodes = [c for c in node.children if c.type == "string_content"]
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

    raise ValueError(f"Unsupported Rust pattern node type: {node_type!r} ({text!r})")


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float, stripping _ separators."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)


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
