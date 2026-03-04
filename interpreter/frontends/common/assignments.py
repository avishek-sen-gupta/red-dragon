"""Common assignment lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend: assignment, augmented_assignment, expression_statement, return.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter.frontends.common.expressions import lower_store_target

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


def lower_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a return statement."""
    children = [c for c in node.children if c.type != "return"]
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


def lower_expression_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower an expression statement (unwrap and lower the inner expr).

    If the inner node is a known statement (e.g. ``while_expression`` in
    Rust), dispatch via ``lower_stmt`` so statement-only handlers are
    reachable.
    """
    for child in node.children:
        if child.type not in (";",) and child.is_named:
            ctx.lower_stmt(child)
            return
    for child in node.children:
        if child.is_named:
            ctx.lower_stmt(child)
