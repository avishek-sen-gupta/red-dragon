# pyright: standard
"""Type annotation extraction utilities for tree-sitter frontends.

Pure functions that extract type text from tree-sitter AST nodes and
normalize language-specific type names to canonical TypeExpr values.

Handles generic/parameterised types structurally: ``List<String>`` in
Java becomes ``ParameterizedType("List", (ScalarType("String"),))``,
``Map<String, Integer>`` becomes
``ParameterizedType("Map", (ScalarType("String"), ScalarType("Int")))``
(with inner types normalised through the type map).
"""

from __future__ import annotations

import logging
from typing import Any

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.types.type_expr import UNKNOWN, ParameterizedType, ScalarType, TypeExpr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic-type AST patterns per language grammar
# ---------------------------------------------------------------------------
# Maps the tree-sitter node type for generic types to the child node type
# that holds the type arguments list.
_GENERIC_TYPE_PATTERNS: dict[str, str] = {
    "generic_type": "type_arguments",  # Java, Scala
    "generic_name": "type_argument_list",  # C#
    "user_type": "type_arguments",  # Kotlin
}

# Kotlin wraps type arguments in type_projection nodes; unwrap them.
_TYPE_PROJECTION_TYPES = frozenset({"type_projection"})


def normalize_type_hint(raw: str, type_map: dict[str, str]) -> TypeExpr:
    """Map a language-specific type name to a canonical TypeExpr.

    Returns ``UNKNOWN`` for empty strings.  Unknown types pass through
    as ``ScalarType(raw)`` (for Object/class types).
    """
    if not raw:
        return UNKNOWN
    return ScalarType(type_map.get(raw, raw))


def extract_type_from_field(
    ctx: TreeSitterEmitContext,
    node: Any,
    field_name: str = "type",  # Any: tree-sitter node — untyped at Python boundary
) -> str:
    """Extract type text from a tree-sitter node's named field.

    Returns the text of the field child, or "" if the field is absent.
    """
    type_node = node.child_by_field_name(field_name)
    return ctx.node_text(type_node) if type_node else ""


def extract_type_from_child(
    ctx: TreeSitterEmitContext,
    node: Any,
    child_types: tuple[str, ...],  # Any: tree-sitter node — untyped at Python boundary
) -> str:
    """Extract type text from the first child matching one of *child_types*.

    Used for languages where types appear as named children rather than
    field-named children (e.g. Kotlin ``user_type``, Pascal ``type``).
    Returns "" if no matching child is found.
    """
    type_child = next(
        (c for c in node.children if c.type in child_types),
        None,
    )
    return ctx.node_text(type_child) if type_child else ""


# ---------------------------------------------------------------------------
# Structured generic type extraction
# ---------------------------------------------------------------------------


def extract_normalized_type(
    ctx: TreeSitterEmitContext,
    node: Any,  # Any: tree-sitter node — untyped at Python boundary
    field_name: str,
    type_map: dict[str, str],
) -> TypeExpr:
    """Extract a type from a node's field, handling generics structurally.

    For generic type nodes (``generic_type``, ``generic_name``, ``user_type``),
    recursively decomposes the AST into ``ParameterizedType`` with each
    component normalised through *type_map*.

    For non-generic nodes, falls back to plain text extraction + normalisation.
    Returns ``UNKNOWN`` if the field is absent.
    """
    type_node = node.child_by_field_name(field_name)
    if not type_node:
        return UNKNOWN
    return _type_node_to_expr(ctx, type_node, type_map)


def extract_normalized_type_from_child(
    ctx: TreeSitterEmitContext,
    node: Any,  # Any: tree-sitter node — untyped at Python boundary
    child_types: tuple[str, ...],
    type_map: dict[str, str],
) -> TypeExpr:
    """Extract a type from a child node, handling generics structurally.

    Like ``extract_type_from_child`` but decomposes generic type AST nodes
    into ``TypeExpr`` with normalised component types.
    Returns ``UNKNOWN`` if no matching child is found.
    """
    type_child = next(
        (c for c in node.children if c.type in child_types),
        None,
    )
    if not type_child:
        return UNKNOWN
    return _type_node_to_expr(ctx, type_child, type_map)


def _type_node_to_expr(
    ctx: TreeSitterEmitContext,
    type_node: Any,  # Any: tree-sitter node — untyped at Python boundary
    type_map: dict[str, str],
) -> TypeExpr:
    """Convert a type AST node to a normalised TypeExpr."""
    args_child_type = _GENERIC_TYPE_PATTERNS.get(type_node.type)
    if args_child_type:
        return _decompose_generic(ctx, type_node, args_child_type, type_map)
    raw = ctx.node_text(type_node)
    return normalize_type_hint(raw, type_map)


def _unwrap_projection(
    node: Any,
) -> Any:  # Any: tree-sitter node — untyped at Python boundary
    """Unwrap Kotlin ``type_projection`` to get the actual type node."""
    if node.type in _TYPE_PROJECTION_TYPES:
        return next((c for c in node.children if c.is_named), node)
    return node


def _decompose_generic(
    ctx: TreeSitterEmitContext,
    node: Any,  # Any: tree-sitter node — untyped at Python boundary
    args_child_type: str,
    type_map: dict[str, str],
) -> TypeExpr:
    """Decompose a generic type node into ``ParameterizedType``.

    Recursively handles nested generics (e.g. ``List<Map<String, Integer>>``).
    Each leaf type name is normalised through *type_map*.
    Unwraps Kotlin ``type_projection`` nodes before processing arguments.
    """
    constructor_expr: TypeExpr = UNKNOWN
    args: list[TypeExpr] = []
    for child in node.children:
        if child.type == args_child_type:
            args = [
                _type_node_to_expr(ctx, _unwrap_projection(arg), type_map)
                for arg in child.children
                if arg.is_named
            ]
        elif child.is_named:
            constructor_expr = normalize_type_hint(ctx.node_text(child), type_map)
    if args and isinstance(constructor_expr, ScalarType):
        return ParameterizedType(constructor_expr.name, tuple(args))
    return constructor_expr
