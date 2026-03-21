"""Parse tree-sitter Scala pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.scala.node_types import ScalaNodeType as NT


def parse_scala_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Scala pattern node to the Pattern ADT."""
    node_type = node.type
    text = ctx.node_text(node)

    if node_type == NT.WILDCARD:
        return WildcardPattern()

    if node_type == NT.INTEGER_LITERAL:
        return LiteralPattern(_parse_number(text))

    if node_type == NT.FLOATING_POINT_LITERAL:
        return LiteralPattern(float(text.replace("_", "")))

    if node_type in (NT.STRING, NT.STRING_LITERAL):
        content = text.strip('"')
        return LiteralPattern(content)

    if node_type == NT.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    if node_type == NT.IDENTIFIER:
        return CapturePattern(text)

    raise ValueError(f"Unsupported Scala pattern node type: {node_type!r} ({text!r})")


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float, stripping _ separators."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)
