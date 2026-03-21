"""Parse tree-sitter Scala pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    AsPattern,
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

    if node_type == NT.ALTERNATIVE_PATTERN:
        return _flatten_alternative_pattern(ctx, node)

    if node_type == NT.TUPLE_PATTERN:
        elements = tuple(
            parse_scala_pattern(ctx, c) for c in node.children if c.is_named
        )
        return SequencePattern(elements)

    if node_type == NT.CASE_CLASS_PATTERN:
        return _parse_case_class_pattern(ctx, node)

    if node_type == NT.TYPED_PATTERN:
        return _parse_typed_pattern(ctx, node)

    if node_type in (NT.STABLE_IDENTIFIER, NT.STABLE_TYPE_IDENTIFIER):
        return ValuePattern(tuple(text.split(".")))

    if node_type == NT.INFIX_PATTERN:
        # Infix patterns like `head :: tail` — treat as wildcard (always matches).
        # Proper cons-list destructuring requires VM support; for now, just match.
        return WildcardPattern()

    raise ValueError(f"Unsupported Scala pattern node type: {node_type!r} ({text!r})")


def _flatten_alternative_pattern(ctx: TreeSitterEmitContext, node) -> OrPattern:
    """Flatten a left-associatively nested alternative_pattern into a flat OrPattern."""
    alternatives = tuple(_collect_alternatives(ctx, node))
    return OrPattern(alternatives)


def _collect_alternatives(ctx: TreeSitterEmitContext, node) -> list[Pattern]:
    """Recursively collect all leaf patterns from a nested alternative_pattern."""
    if node.type != NT.ALTERNATIVE_PATTERN:
        return [parse_scala_pattern(ctx, node)]
    return [
        leaf
        for child in node.children
        if child.is_named
        for leaf in _collect_alternatives(ctx, child)
    ]


def _parse_case_class_pattern(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse case_class_pattern: Circle(r), Point(x, y)."""
    type_node = next(
        c
        for c in node.children
        if c.type in (NT.TYPE_IDENTIFIER, NT.IDENTIFIER, NT.STABLE_TYPE_IDENTIFIER)
    )
    class_name = ctx.node_text(type_node)
    positional = tuple(
        parse_scala_pattern(ctx, c)
        for c in node.children
        if c.is_named and c != type_node
    )
    return ClassPattern(class_name, positional=positional, keyword=())


def _parse_typed_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Parse typed_pattern: i: Int → AsPattern(ClassPattern('Int', (), ()), 'i').

    For wildcard typed patterns (_: Int), return just ClassPattern (no binding).
    """
    named = [c for c in node.children if c.is_named]
    var_node = named[0]
    type_name = ctx.node_text(named[1])
    class_pat = ClassPattern(type_name, positional=(), keyword=())

    if var_node.type == NT.WILDCARD:
        return class_pat
    return AsPattern(class_pat, ctx.node_text(var_node))


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float, stripping _ separators."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)
