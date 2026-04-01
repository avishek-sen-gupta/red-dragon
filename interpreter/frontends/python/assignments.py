# pyright: standard
"""Python-specific assignment lowerers -- pure functions taking (ctx, node).

These override common assignment lowerers to use Python's store_target
which supports tuple/pattern_list unpacking.
"""

from __future__ import annotations

from typing import Any

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.frontends.python.expressions import lower_store_target
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import Binop


def lower_assignment(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_store_target(ctx, left, val_reg, node)  # type: ignore[arg-type]  # see red-dragon-hzmm


def lower_augmented_assignment(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    op_node = [c for c in node.children if c.type not in (left.type, right.type)][0]
    op_text = ctx.node_text(op_node).rstrip("=")
    lhs_reg = ctx.lower_expr(left)
    rhs_reg = ctx.lower_expr(right)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(op_text),
            left=lhs_reg,
            right=rhs_reg,
        ),
        node=node,
    )
    lower_store_target(ctx, left, result, node)  # type: ignore[arg-type]  # see red-dragon-hzmm
