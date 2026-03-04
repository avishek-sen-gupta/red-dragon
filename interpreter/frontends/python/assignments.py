"""Python-specific assignment lowerers -- pure functions taking (ctx, node).

These override common assignment lowerers to use Python's store_target
which supports tuple/pattern_list unpacking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter.frontends.python.expressions import lower_store_target

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


def lower_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_store_target(ctx, left, val_reg, node)


def lower_augmented_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    op_node = [c for c in node.children if c.type not in (left.type, right.type)][0]
    op_text = ctx.node_text(op_node).rstrip("=")
    lhs_reg = ctx.lower_expr(left)
    rhs_reg = ctx.lower_expr(right)
    result = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result,
        operands=[op_text, lhs_reg, rhs_reg],
        node=node,
    )
    lower_store_target(ctx, left, result, node)
