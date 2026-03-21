"""Parse tree-sitter Ruby case/in pattern nodes into the Pattern ADT.

Diagnostic-confirmed node types (ruby_pattern_diag.py):
  integer            → LiteralPattern(int)
  unary(-,integer)   → LiteralPattern(negative int)
  string             → LiteralPattern(str)
  identifier '_'     → WildcardPattern()
  identifier other   → CapturePattern(name)
  constant           → ClassPattern(name, positional=(), keyword=())
  alternative_pattern→ OrPattern(alternatives)
  array_pattern      → SequencePattern(elements) or ClassPattern with leading constant
  as_pattern         → AsPattern(inner_pattern, name)
  splat_parameter    → StarPattern(name) or StarPattern('_') for anonymous
  hash_pattern       → MappingPattern(entries)
  keyword_pattern    → (key, value_pattern) pair for MappingPattern
"""

from __future__ import annotations

import logging

from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    MappingPattern,
    OrPattern,
    Pattern,
    SequencePattern,
    StarPattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.ruby.node_types import RubyNodeType as RNT

logger = logging.getLogger(__name__)


def parse_ruby_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Ruby pattern node to the Pattern ADT."""
    node_type = node.type

    if node_type == RNT.INTEGER:
        return LiteralPattern(int(ctx.node_text(node)))

    if node_type == RNT.FLOAT:
        return LiteralPattern(float(ctx.node_text(node)))

    if node_type == RNT.UNARY:
        return _parse_unary_pattern(ctx, node)

    if node_type == RNT.STRING:
        return LiteralPattern(_extract_string_content(ctx, node))

    if node_type == RNT.TRUE:
        return LiteralPattern(True)

    if node_type == RNT.FALSE:
        return LiteralPattern(False)

    if node_type == RNT.NIL:
        return LiteralPattern(None)

    if node_type == RNT.IDENTIFIER:
        text = ctx.node_text(node)
        if text == "_":
            return WildcardPattern()
        return CapturePattern(text)

    if node_type == RNT.CONSTANT:
        return ClassPattern(ctx.node_text(node), positional=(), keyword=())

    if node_type == RNT.ALTERNATIVE_PATTERN:
        return _parse_alternative_pattern(ctx, node)

    if node_type == RNT.ARRAY_PATTERN:
        return _parse_array_pattern(ctx, node)

    if node_type == RNT.AS_PATTERN:
        return _parse_as_pattern(ctx, node)

    if node_type == RNT.SPLAT_PARAMETER:
        return _parse_splat_parameter(ctx, node)

    if node_type == RNT.HASH_PATTERN:
        return _parse_hash_pattern(ctx, node)

    raise ValueError(
        f"Unsupported Ruby pattern node type: {node_type!r} ({ctx.node_text(node)!r})"
    )


def _parse_unary_pattern(ctx: TreeSitterEmitContext, node) -> LiteralPattern:
    """Parse a unary negation node like -1 into a LiteralPattern."""
    # Unary: operator child + operand child
    operator = next(
        (c for c in node.children if not c.is_named and c.type == "-"),
        None,
    )
    operand = next((c for c in node.children if c.is_named), None)
    if operator and operand and operand.type == RNT.INTEGER:
        return LiteralPattern(-int(ctx.node_text(operand)))
    if operator and operand and operand.type == RNT.FLOAT:
        return LiteralPattern(-float(ctx.node_text(operand)))
    raise ValueError(f"Unsupported unary pattern: {ctx.node_text(node)!r}")


def _extract_string_content(ctx: TreeSitterEmitContext, node) -> str:
    """Extract the text content from a string node."""
    content_node = next(
        (c for c in node.children if c.type == RNT.STRING_CONTENT),
        None,
    )
    if content_node:
        return ctx.node_text(content_node)
    # Empty string: no string_content child
    return ""


def _parse_alternative_pattern(ctx: TreeSitterEmitContext, node) -> OrPattern:
    """Parse alternative_pattern (1 | 2 | 3) into a flat OrPattern."""
    alternatives = tuple(
        parse_ruby_pattern(ctx, c) for c in node.children if c.is_named
    )
    return OrPattern(alternatives)


def _parse_array_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Parse array_pattern ([a, b] or Point[x, y]) into SequencePattern or ClassPattern."""
    leading_constant = next(
        (c for c in node.children if c.is_named and c.type == RNT.CONSTANT),
        None,
    )
    element_nodes = [
        c for c in node.children if c.is_named and c.type not in (RNT.CONSTANT,)
    ]
    elements = tuple(parse_ruby_pattern(ctx, c) for c in element_nodes)
    if leading_constant:
        class_name = ctx.node_text(leading_constant)
        return _resolve_positional_via_match_args(ctx, class_name, elements)
    return SequencePattern(elements)


def _parse_as_pattern(ctx: TreeSitterEmitContext, node) -> AsPattern:
    """Parse as_pattern (pattern => name) into AsPattern."""
    named_children = [c for c in node.children if c.is_named]
    # First named child is the inner pattern, last named child is the binding name
    inner_node = named_children[0]
    name_node = named_children[-1]
    inner_pattern = parse_ruby_pattern(ctx, inner_node)
    return AsPattern(inner_pattern, ctx.node_text(name_node))


def _parse_splat_parameter(ctx: TreeSitterEmitContext, node) -> StarPattern:
    """Parse splat_parameter (*rest or *) into StarPattern."""
    name_node = next(
        (c for c in node.children if c.is_named and c.type == RNT.IDENTIFIER),
        None,
    )
    name = ctx.node_text(name_node) if name_node else "_"
    return StarPattern(name)


def _parse_hash_pattern(ctx: TreeSitterEmitContext, node) -> MappingPattern:
    """Parse hash_pattern ({name: n, age: a}) into MappingPattern."""
    keyword_patterns = [c for c in node.children if c.type == RNT.KEYWORD_PATTERN]
    entries = tuple(_parse_keyword_pattern(ctx, kp) for kp in keyword_patterns)
    return MappingPattern(entries)


def _parse_keyword_pattern(ctx: TreeSitterEmitContext, node) -> tuple[str, Pattern]:
    """Parse a keyword_pattern (name: value) into a (key, Pattern) pair.

    If no value is present ({name:} shorthand), the key becomes a capture variable.
    """
    key_node = next(c for c in node.children if c.type == RNT.HASH_KEY_SYMBOL)
    key = ctx.node_text(key_node)
    value_node = next(
        (c for c in node.children if c.is_named and c.type != RNT.HASH_KEY_SYMBOL),
        None,
    )
    value_pattern: Pattern = (
        parse_ruby_pattern(ctx, value_node) if value_node else CapturePattern(key)
    )
    return (key, value_pattern)


def _resolve_positional_via_match_args(
    ctx: TreeSitterEmitContext, class_name: str, positional: tuple[Pattern, ...]
) -> ClassPattern:
    """Convert positional args to keyword args via match_args if available."""
    class_info = ctx.symbol_table.classes.get(class_name)
    match_args = list(class_info.match_args) if class_info else []
    if positional and match_args:
        keyword = tuple(
            (match_args[i], pat)
            for i, pat in enumerate(positional)
            if i < len(match_args)
        )
        return ClassPattern(class_name, positional=(), keyword=keyword)
    return ClassPattern(class_name, positional=positional, keyword=())
