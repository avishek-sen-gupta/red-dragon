"""Common control-flow lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend: if/elif/while/for/break/continue.
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.node_types import CommonNodeType

from interpreter.ir import Opcode


def lower_if(ctx: TreeSitterEmitContext, node) -> None:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    if alt_node:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            node=node,
        )
    else:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        lower_alternative(ctx, alt_node, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_alternative(ctx: TreeSitterEmitContext, alt_node, end_label: str) -> None:
    """Lower an else/elif/else-if alternative block."""
    alt_type = alt_node.type
    if alt_type in (CommonNodeType.ELIF_CLAUSE,):
        lower_elif(ctx, alt_node, end_label)
    elif alt_type in (CommonNodeType.ELSE_CLAUSE, CommonNodeType.ELSE):
        body = alt_node.child_by_field_name("body")
        if body:
            ctx.lower_block(body)
        else:
            for child in alt_node.children:
                if child.type not in (
                    CommonNodeType.ELSE,
                    CommonNodeType.COLON,
                    CommonNodeType.OPEN_BRACE,
                    CommonNodeType.CLOSE_BRACE,
                ):
                    ctx.lower_stmt(child)
    else:
        ctx.lower_block(alt_node)


def lower_elif(ctx: TreeSitterEmitContext, node, end_label: str) -> None:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("elif_true")
    false_label = ctx.fresh_label("elif_false") if alt_node else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        lower_alternative(ctx, alt_node, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)


def lower_break(ctx: TreeSitterEmitContext, node) -> None:
    """Lower break statement as BRANCH to innermost break target."""
    if ctx.break_target_stack:
        ctx.emit(
            Opcode.BRANCH,
            label=ctx.break_target_stack[-1],
            node=node,
        )
    else:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["break_outside_loop_or_switch"],
            node=node,
        )


def lower_continue(ctx: TreeSitterEmitContext, node) -> None:
    """Lower continue statement as BRANCH to innermost loop continue label."""
    if ctx.loop_stack:
        ctx.emit(
            Opcode.BRANCH,
            label=ctx.loop_stack[-1]["continue_label"],
            node=node,
        )
    else:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["continue_outside_loop"],
            node=node,
        )


def lower_while(ctx: TreeSitterEmitContext, node) -> None:
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_c_style_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a C-style for(init; cond; update) loop."""
    init_node = node.child_by_field_name("initializer")
    cond_node = node.child_by_field_name(ctx.constants.for_condition_field)
    update_node = node.child_by_field_name(ctx.constants.for_update_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    if init_node:
        ctx.lower_stmt(init_node)

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    if cond_node:
        cond_reg = ctx.lower_expr(cond_node)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            node=node,
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=body_label)
    update_label = ctx.fresh_label("for_update") if update_node else loop_label
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    if update_node:
        ctx.emit(Opcode.LABEL, label=update_label)
        ctx.lower_expr(update_node)
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)
