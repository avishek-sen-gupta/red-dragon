"""Parse tree-sitter Python pattern AST nodes into Pattern ADT."""

from __future__ import annotations

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
from interpreter.frontends.python.node_types import PythonNodeType

_WILDCARD = "_"


def _find_module_root(node) -> object:
    """Walk up via .parent to reach the module root node."""
    current = node
    while current.parent:
        current = current.parent
    return current


def _find_class_def(node, class_name: str):
    """Recursively find a class_definition node with matching name."""
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node and name_node.text.decode() == class_name:
            return node
    return next(
        (
            result
            for child in node.children
            if (result := _find_class_def(child, class_name))
        ),
        None,
    )


def _extract_match_args_from_body(body) -> list[str]:
    """Extract field names from __match_args__ = ("x", "y") in a class body."""
    for child in body.children:
        if child.type != "assignment":
            continue
        left = child.child_by_field_name("left")
        right = child.child_by_field_name("right")
        if (
            left
            and left.text.decode() == "__match_args__"
            and right
            and right.type == "tuple"
        ):
            return [
                sc.text.decode()
                for s in right.children
                if s.type == "string"
                for sc in s.children
                if sc.type == "string_content"
            ]
    return []


def _resolve_match_args(node, class_name: str) -> list[str]:
    """Find __match_args__ for class_name by walking the AST."""
    root = _find_module_root(node)
    class_def = _find_class_def(root, class_name)
    if class_def is None:
        return []
    body = class_def.child_by_field_name("body")
    if body is None:
        return []
    return _extract_match_args_from_body(body)


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


def parse_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
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

    # Capture (identifier or dotted_name with single segment)
    if node_type in ("identifier", "dotted_name"):
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
            match_args = _resolve_match_args(node, class_name)
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
