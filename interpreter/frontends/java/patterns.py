# pyright: standard
"""Parse tree-sitter Java pattern nodes into Pattern ADT."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext


def parse_java_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Convert a Java tree-sitter pattern node into a Pattern ADT.

    Java 16+ pattern nodes in switch expressions:
      pattern → type_pattern | record_pattern
      type_pattern: Type identifier (e.g., String s, String _)
      record_pattern: Type(components) (e.g., Point(int x, int y))
    """
    # Unwrap the outer 'pattern' wrapper node
    if node.type == "pattern":
        inner = next((c for c in node.children if c.is_named), node)
        return parse_java_pattern(ctx, inner)

    if node.type == "type_pattern":
        return _parse_type_pattern(ctx, node)

    if node.type == "record_pattern":
        return _parse_record_pattern(ctx, node)

    # Identifier: wildcard _ or capture
    if node.type == "identifier":
        text = ctx.node_text(node)
        if text == "_":
            return WildcardPattern()
        return CapturePattern(name=text)

    # Fallback: treat as literal
    text = ctx.node_text(node)
    return LiteralPattern(value=text)


def _parse_type_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Parse: String s, String _, int x."""
    named = [c for c in node.children if c.is_named]
    type_node = named[0] if named else node
    name_node = named[1] if len(named) >= 2 else None

    type_name = ctx.node_text(type_node)
    class_pat = ClassPattern(class_name=type_name, positional=(), keyword=())

    if name_node:
        var_name = ctx.node_text(name_node)
        if var_name == "_":
            return class_pat
        return AsPattern(pattern=class_pat, name=var_name)

    return class_pat


def _parse_record_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Parse: Point(int x, int y)."""
    type_node = next(
        (c for c in node.children if c.type in ("type_identifier", "identifier")),
        None,
    )
    class_name = ctx.node_text(type_node) if type_node else "Object"

    body = next(
        (c for c in node.children if c.type == "record_pattern_body"),
        None,
    )
    positional: list[Pattern] = []
    if body:
        components = [c for c in body.children if c.type == "record_pattern_component"]
        positional = [_parse_record_component(ctx, comp) for comp in components]

    return ClassPattern(class_name=class_name, positional=tuple(positional), keyword=())


def _parse_record_component(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Parse a record_pattern_component: int x, String s, _."""
    named = [c for c in node.children if c.is_named]
    if len(named) >= 2:
        # Typed binding: int x → capture x
        name_node = named[-1]
        var_name = ctx.node_text(name_node)
        if var_name == "_":
            return WildcardPattern()
        return CapturePattern(name=var_name)
    if len(named) == 1:
        text = ctx.node_text(named[0])
        if text == "_":
            return WildcardPattern()
        return CapturePattern(name=text)
    return WildcardPattern()
