"""Ruby-specific assignment lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter.frontends.ruby.expressions import lower_ruby_store_target

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


def lower_ruby_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Ruby return statement."""
    children = [
        c for c in node.children if c.type not in ("return", "return_statement")
    ]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.default_return_value],
        )
    ctx.emit(
        Opcode.RETURN,
        operands=[val_reg],
        node=node,
    )


def lower_ruby_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Ruby assignment using Ruby-specific store target."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_ruby_store_target(ctx, left, val_reg, node)


def lower_ruby_augmented_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Ruby operator_assignment using Ruby-specific store target."""
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
    lower_ruby_store_target(ctx, left, result, node)
