"""C-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel
from interpreter.frontends.c.node_types import CNodeType

logger = logging.getLogger(__name__)


def lower_do_while(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (cond);"""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=cond_label)
    if cond_node:
        cond_reg = ctx.lower_expr(cond_node)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{body_label},{end_label}"),
            node=node,
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch(expr) { case ... } as an if/else chain."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node)
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    cases = (
        [c for c in body_node.children if c.type == CNodeType.CASE_STATEMENT]
        if body_node
        else []
    )

    for case in cases:
        value_node = case.child_by_field_name("value")
        body_stmts = [
            c
            for c in case.children
            if c.is_named
            and c.type not in (CNodeType.CASE, CNodeType.DEFAULT)
            and c != value_node
        ]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if value_node:
            case_reg = ctx.lower_expr(value_node)
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=["==", subject_reg, case_reg],
                node=case,
            )
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cmp_reg],
                label=CodeLabel(f"{arm_label},{next_label}"),
            )
        else:
            # default case
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_case_as_block(ctx: TreeSitterEmitContext, node) -> None:
    """Defensive handler for case_statement encountered via lower_block.

    In normal flow, case_statement is consumed by lower_switch which
    manually extracts cases from the compound_statement body. This handler
    exists as a safety net.
    """
    value_node = node.child_by_field_name("value")
    for child in node.children:
        if child.is_named and child != value_node:
            ctx.lower_stmt(child)


def lower_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto_statement as BRANCH user_{label}."""
    label_node = next(
        (c for c in node.children if c.type == CNodeType.STATEMENT_IDENTIFIER), None
    )
    if label_node:
        target_label = CodeLabel(f"user_{ctx.node_text(label_node)}")
        ctx.emit(
            Opcode.BRANCH,
            label=target_label,
            node=node,
        )
    else:
        logger.warning("goto without label: %s", ctx.node_text(node)[:40])


def lower_labeled_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower labeled_statement: emit label then lower the inner statement."""
    label_node = next(
        (c for c in node.children if c.type == CNodeType.STATEMENT_IDENTIFIER), None
    )
    if label_node:
        ctx.emit(Opcode.LABEL, label=CodeLabel(f"user_{ctx.node_text(label_node)}"))
    # Lower the actual statement within the label
    for child in node.children:
        if child.is_named and child.type != CNodeType.STATEMENT_IDENTIFIER:
            ctx.lower_stmt(child)


def lower_linkage_spec(ctx: TreeSitterEmitContext, node) -> None:
    """Lower extern 'C' { ... } — just lower the body declarations."""
    for child in node.children:
        if child.is_named and child.type != CNodeType.STRING_LITERAL:
            ctx.lower_stmt(child)
