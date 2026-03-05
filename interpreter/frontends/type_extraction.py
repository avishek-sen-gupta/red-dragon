"""Type annotation extraction utilities for tree-sitter frontends.

Pure functions that extract type text from tree-sitter AST nodes and
normalize language-specific type names to canonical TypeName values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


def normalize_type_hint(raw: str, type_map: dict[str, str]) -> str:
    """Map a language-specific type name to a canonical TypeName value.

    Unknown types pass through as-is (for Object/class types).
    """
    return type_map.get(raw, raw)


def extract_type_from_field(
    ctx: TreeSitterEmitContext, node, field_name: str = "type"
) -> str:
    """Extract type text from a tree-sitter node's named field.

    Returns the text of the field child, or "" if the field is absent.
    """
    type_node = node.child_by_field_name(field_name)
    return ctx.node_text(type_node) if type_node else ""


def extract_type_from_child(
    ctx: TreeSitterEmitContext, node, child_types: tuple[str, ...]
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
