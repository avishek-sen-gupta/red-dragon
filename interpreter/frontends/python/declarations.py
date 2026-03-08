"""Python-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.declarations import lower_class_def
from interpreter.frontends.python.node_types import PythonNodeType


def _extract_python_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class names from a Python class_definition node.

    In tree-sitter Python, superclasses are inside an ``argument_list``
    child containing ``identifier`` children.
    """
    arg_list = next(
        (c for c in node.children if c.type == PythonNodeType.ARGUMENT_LIST),
        None,
    )
    if arg_list is None:
        return []
    return [
        ctx.node_text(c)
        for c in arg_list.children
        if c.type == PythonNodeType.IDENTIFIER
    ]


def lower_python_class_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Python class_definition, extracting parents for inheritance."""
    parents = _extract_python_parents(ctx, node)
    lower_class_def(ctx, node, parents=parents)
