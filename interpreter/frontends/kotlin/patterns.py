"""Parse tree-sitter Kotlin when-condition nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    Pattern,
)
from interpreter.frontends.common.pattern_utils import parse_number
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT

_STRING_CONTENT = "string_content"


def parse_kotlin_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Kotlin when-condition inner node to the Pattern ADT."""
    node_type = node.type
    text = ctx.node_text(node)

    if node_type in (KNT.INTEGER_LITERAL, KNT.LONG_LITERAL, KNT.HEX_LITERAL):
        return LiteralPattern(parse_number(text, strip_suffixes="lLuU"))

    if node_type == KNT.REAL_LITERAL:
        return LiteralPattern(float(text.replace("_", "").rstrip("fFdD")))

    if node_type == KNT.STRING_LITERAL:
        content_nodes = [c for c in node.children if c.type == _STRING_CONTENT]
        content = ctx.node_text(content_nodes[0]) if content_nodes else ""
        return LiteralPattern(content)

    if node_type == KNT.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    if node_type == KNT.NULL_LITERAL:
        return LiteralPattern(None)

    if node_type == KNT.SIMPLE_IDENTIFIER:
        return CapturePattern(text)

    if node_type in (KNT.CHECK_EXPRESSION, KNT.TYPE_TEST):
        return _parse_type_check(ctx, node)

    raise ValueError(f"Unsupported Kotlin pattern node type: {node_type!r} ({text!r})")


def _parse_type_check(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse `is Type` as ClassPattern for isinstance check.

    Tree-sitter structure:
      type_test
        is              (anonymous)
        user_type
          type_identifier  (named)
    """
    type_node = next(
        (
            c
            for c in node.children
            if c.type in (KNT.USER_TYPE, KNT.TYPE_IDENTIFIER, KNT.NULLABLE_TYPE)
        ),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    return ClassPattern(type_name, positional=(), keyword=())
