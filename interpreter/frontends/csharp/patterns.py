"""Parse tree-sitter C# pattern nodes into Pattern ADT."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.common.patterns import (
    AndPattern,
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    NegatedPattern,
    OrPattern,
    Pattern,
    RelationalPattern,
    SequencePattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT


def parse_csharp_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Convert a C# tree-sitter pattern node into a Pattern ADT."""
    node_type = node.type

    # Discard: _
    if node_type == NT.DISCARD:
        return WildcardPattern()

    # Constant pattern: null, 0, "hello", etc.
    if node_type == NT.CONSTANT_PATTERN:
        inner = next((c for c in node.children if c.is_named), node)
        return _parse_constant(ctx, inner)

    # Declaration pattern: int i, string s, var x
    if node_type == NT.DECLARATION_PATTERN:
        named = [c for c in node.children if c.is_named]
        type_node = named[0] if named else node
        name_node = named[1] if len(named) >= 2 else named[0]
        var_name = ctx.node_text(name_node)
        # var x (implicit_type) → just capture, no type check
        if type_node.type == "implicit_type":
            return CapturePattern(name=var_name)
        # Explicit type → type check + binding
        type_name = ctx.node_text(type_node)
        return AsPattern(
            pattern=ClassPattern(class_name=type_name, positional=(), keyword=()),
            name=var_name,
        )

    # Recursive pattern: Circle { Radius: 0 }
    if node_type == NT.RECURSIVE_PATTERN:
        type_node = next(
            (
                c
                for c in node.children
                if c.type in ("identifier", "predefined_type", "generic_name")
            ),
            None,
        )
        class_name = ctx.node_text(type_node) if type_node else "Object"
        prop_clause = next(
            (c for c in node.children if c.type == NT.PROPERTY_PATTERN_CLAUSE),
            None,
        )
        keyword: list[tuple[str, Pattern]] = []
        if prop_clause:
            subpatterns = [c for c in prop_clause.children if c.type == NT.SUBPATTERN]
            for sub in subpatterns:
                sub_named = [c for c in sub.children if c.is_named]
                if len(sub_named) >= 2:
                    prop_name = ctx.node_text(sub_named[0])
                    prop_pattern = parse_csharp_pattern(ctx, sub_named[1])
                    keyword.append((prop_name, prop_pattern))
        return ClassPattern(
            class_name=class_name, positional=(), keyword=tuple(keyword)
        )

    # Identifier used as a pattern
    if node_type == "identifier":
        text = ctx.node_text(node)
        if text == "_":
            return WildcardPattern()
        return CapturePattern(name=text)

    # Parenthesized pattern: (pattern) — unwrap and parse inner
    if node_type == NT.PARENTHESIZED_PATTERN:
        inner = next((c for c in node.children if c.is_named), node)
        return parse_csharp_pattern(ctx, inner)

    # Or pattern: pattern1 or pattern2
    if node_type == NT.OR_PATTERN:
        alternatives = [
            parse_csharp_pattern(ctx, c) for c in node.children if c.is_named
        ]
        return OrPattern(alternatives=tuple(alternatives))

    # List pattern: [1, 2, ..]
    if node_type == NT.LIST_PATTERN:
        elements = [parse_csharp_pattern(ctx, c) for c in node.children if c.is_named]
        return SequencePattern(elements=tuple(elements))

    # Relational pattern: > 5, < 10, >= 0, <= 100
    if node_type == NT.RELATIONAL_PATTERN:
        children = [c for c in node.children if c.is_named]
        op_node = next(
            (c for c in node.children if not c.is_named and c.type not in ("(", ")")),
            None,
        )
        operator = ctx.node_text(op_node) if op_node else ">"
        value_node = children[0] if children else node
        return RelationalPattern(
            operator=operator, value=_parse_const_value(ctx, value_node)
        )

    # And pattern: pattern1 and pattern2
    if node_type == NT.AND_PATTERN:
        named = [c for c in node.children if c.is_named]
        left = parse_csharp_pattern(ctx, named[0])
        right = parse_csharp_pattern(ctx, named[1])
        return AndPattern(left=left, right=right)

    # Negated pattern: not pattern
    if node_type == NT.NEGATED_PATTERN:
        inner = next((c for c in node.children if c.is_named), node)
        return NegatedPattern(inner=parse_csharp_pattern(ctx, inner))

    # Fallback: treat as literal
    return _parse_constant(ctx, node)


def _parse_constant(
    ctx: TreeSitterEmitContext, node: Any
) -> LiteralPattern:  # Any: tree-sitter node — untyped at Python boundary
    """Parse a constant value node into a LiteralPattern."""
    return LiteralPattern(value=_parse_const_value(ctx, node))


def _parse_const_value(
    ctx: TreeSitterEmitContext, node: Any
) -> object:  # Any: tree-sitter node — untyped at Python boundary
    """Parse a constant value node into a Python value."""
    text = ctx.node_text(node)
    match node.type:
        case "null_literal":
            return None
        case "integer_literal":
            return int(text)
        case "real_literal":
            return float(text)
        case "string_literal":
            return text.strip('"')
        case "character_literal":
            return text.strip("'")
        case "boolean_literal":
            return text == "true"
        case _:
            return text
