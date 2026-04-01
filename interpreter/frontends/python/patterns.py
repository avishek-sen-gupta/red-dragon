# pyright: standard
"""Parse tree-sitter Python pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from typing import Any

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
    ValuePattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.python.node_types import PythonNodeType
from interpreter.class_name import ClassName

_WILDCARD = "_"


def _parse_key_literal(
    ctx: TreeSitterEmitContext, node
) -> int | float | str | bool | None:
    """Extract a literal value from a dict pattern key node."""
    text = ctx.node_text(node)
    match node.type:
        case "integer":
            return int(text)
        case "float":
            return float(text)
        case "true":
            return True
        case "false":
            return False
        case "none":
            return None
        case _:  # string
            return text.strip("'\"")


def parse_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Pattern:  # Any: tree-sitter node — untyped at Python boundary
    """Convert a tree-sitter case_pattern (or inner pattern) node into a Pattern ADT."""
    # case_pattern is a wrapper — unwrap to inner
    if node.type == PythonNodeType.CASE_PATTERN:
        named = [c for c in node.children if c.is_named]
        return parse_pattern(ctx, named[0]) if named else WildcardPattern()

    node_type = node.type
    text = ctx.node_text(node)

    # Wildcard
    if text == _WILDCARD:
        return WildcardPattern()

    # Literals
    if node_type == "integer":
        return LiteralPattern(value=int(text))
    if node_type == "float":
        return LiteralPattern(value=float(text))
    if node_type == "string":
        content = text.strip("'\"")
        return LiteralPattern(value=content)
    if node_type == "true":
        return LiteralPattern(value=True)
    if node_type == "false":
        return LiteralPattern(value=False)
    if node_type == "none":
        return LiteralPattern(value=None)

    # Capture vs value pattern
    if node_type in ("identifier", "dotted_name"):
        # Multi-segment dotted_name (e.g., Color.RED) = value pattern
        if node_type == "dotted_name":
            identifiers = [c for c in node.children if c.type == "identifier"]
            if len(identifiers) > 1:
                return ValuePattern(parts=tuple(ctx.node_text(c) for c in identifiers))
        return CapturePattern(name=text)

    # Splat/star pattern
    if node_type == PythonNodeType.SPLAT_PATTERN:
        named = [c for c in node.children if c.is_named]
        name = ctx.node_text(named[0]) if named else "_"
        return StarPattern(name=name)

    # Tuple pattern
    if node_type == PythonNodeType.TUPLE_PATTERN:
        elements = tuple(
            parse_pattern(ctx, c)
            for c in node.children
            if c.type in (PythonNodeType.CASE_PATTERN, PythonNodeType.SPLAT_PATTERN)
        )
        return SequencePattern(elements=elements)

    # List pattern
    if node_type == PythonNodeType.LIST_PATTERN:
        elements = tuple(
            parse_pattern(ctx, c)
            for c in node.children
            if c.type in (PythonNodeType.CASE_PATTERN, PythonNodeType.SPLAT_PATTERN)
        )
        return SequencePattern(elements=elements)

    # Dict pattern
    if node_type == PythonNodeType.DICT_PATTERN:
        _KEY_TYPES = frozenset({"string", "integer", "float", "true", "false", "none"})
        key_nodes = [c for c in node.children if c.type in _KEY_TYPES]
        val_nodes = [c for c in node.children if c.type == PythonNodeType.CASE_PATTERN]
        entries = tuple(
            (_parse_key_literal(ctx, k), parse_pattern(ctx, v))
            for k, v in zip(key_nodes, val_nodes)
        )
        return MappingPattern(entries=entries)

    # Class pattern
    if node_type == PythonNodeType.CLASS_PATTERN:
        dotted = next(c for c in node.children if c.type == "dotted_name")
        class_name = ctx.node_text(dotted)
        case_patterns = [
            c for c in node.children if c.type == PythonNodeType.CASE_PATTERN
        ]
        positional: list[Pattern] = []
        keyword: list[tuple[str, Pattern]] = []
        for child in case_patterns:
            inner = next(c for c in child.children if c.is_named)
            if inner.type == PythonNodeType.KEYWORD_PATTERN:
                parts = [c for c in inner.children if c.is_named]
                kw_name = ctx.node_text(parts[0])
                kw_val = parse_pattern(ctx, parts[1])
                keyword.append((kw_name, kw_val))
            else:
                positional.append(parse_pattern(ctx, child))
        # Resolve positional args via __match_args__ if available
        if positional:
            class_info = ctx.symbol_table.classes.get(ClassName(class_name))
            match_args = list(class_info.match_args) if class_info else []
            if match_args:
                keyword.extend(
                    (match_args[i], pat)
                    for i, pat in enumerate(positional)
                    if i < len(match_args)
                )
                positional = []
        return ClassPattern(
            class_name=class_name,
            positional=tuple(positional),
            keyword=tuple(keyword),
        )

    # Union pattern (or-pattern)
    if node_type == PythonNodeType.UNION_PATTERN:
        alternatives = tuple(parse_pattern(ctx, c) for c in node.children if c.is_named)
        return OrPattern(alternatives=alternatives)

    # As pattern
    if node_type == PythonNodeType.AS_PATTERN:
        named = [c for c in node.children if c.is_named]
        inner = parse_pattern(ctx, named[0]) if named else WildcardPattern()
        bind_name = ctx.node_text(named[-1]) if len(named) >= 2 else "_"
        return AsPattern(pattern=inner, name=bind_name)

    # Fallback: treat as capture
    return CapturePattern(name=text)
