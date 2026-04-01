# pyright: standard
"""Pascal type extraction helpers."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.type_extraction import normalize_type_hint
from interpreter.frontends.pascal.node_types import PascalNodeType
from interpreter.types.type_expr import UNKNOWN, TypeExpr


def extract_pascal_return_type(ctx: TreeSitterEmitContext, search_node) -> TypeExpr:
    """Extract the return type from a Pascal function declaration node.

    Pascal functions (kFunction) have a ``typeref`` child containing the return
    type.  Procedures (kProcedure) have no return type.

    Returns a normalized TypeExpr, or ``UNKNOWN`` if the node is a procedure.
    """
    is_function = any(c.type == PascalNodeType.K_FUNCTION for c in search_node.children)
    if not is_function:
        return UNKNOWN
    # typeref may be nested inside a type node or be a direct child
    type_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.TYPE), None
    )
    if type_node is not None:
        typeref = next(
            (c for c in type_node.children if c.type == PascalNodeType.TYPEREF), None
        )
    else:
        typeref = next(
            (c for c in search_node.children if c.type == PascalNodeType.TYPEREF), None
        )
    if typeref is None:
        return UNKNOWN
    id_node = next(
        (c for c in typeref.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    raw = ctx.node_text(id_node) if id_node else ctx.node_text(typeref)
    return normalize_type_hint(raw.lower(), ctx.type_map)
