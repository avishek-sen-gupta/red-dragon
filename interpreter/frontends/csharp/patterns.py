"""Parse tree-sitter C# pattern nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT


def parse_csharp_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
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

    # Fallback: treat as literal
    return _parse_constant(ctx, node)


def _parse_constant(ctx: TreeSitterEmitContext, node) -> LiteralPattern:
    """Parse a constant value node into a LiteralPattern."""
    text = ctx.node_text(node)
    match node.type:
        case "null_literal":
            return LiteralPattern(value=None)
        case "integer_literal":
            return LiteralPattern(value=int(text))
        case "real_literal":
            return LiteralPattern(value=float(text))
        case "string_literal":
            return LiteralPattern(value=text.strip('"'))
        case "character_literal":
            return LiteralPattern(value=text.strip("'"))
        case "boolean_literal":
            return LiteralPattern(value=text == "true")
        case _:
            return LiteralPattern(value=text)
