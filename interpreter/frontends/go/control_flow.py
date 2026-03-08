"""Go-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.frontends.go.expressions import (
    extract_expression_list,
    lower_expression_list,
    lower_go_store_target,
)
from interpreter.frontends.go.node_types import GoNodeType

logger = logging.getLogger(__name__)


# -- Go: if statement ------------------------------------------------------


def lower_go_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Go if statement, including optional init statement.

    Go allows ``if x := expr; cond { }``.  The init variable is scoped
    to the entire if/else chain.
    """
    init_node = node.child_by_field_name("initializer")
    scope_entered = init_node is not None and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()
    if init_node:
        ctx.lower_stmt(init_node)

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
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        # alt_node may be a block (else) or an if_statement (else if)
        if alt_node.type == GoNodeType.IF_STATEMENT:
            lower_go_if(ctx, alt_node)
        else:
            ctx.lower_block(alt_node)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    if scope_entered:
        ctx.exit_block_scope()


# -- Go: for statement -----------------------------------------------------


def lower_go_for(ctx: TreeSitterEmitContext, node) -> None:
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    # Look for for_clause (C-style) or range_clause
    for_clause = next(
        (c for c in node.children if c.type == GoNodeType.FOR_CLAUSE), None
    )
    range_clause = next(
        (c for c in node.children if c.type == GoNodeType.RANGE_CLAUSE), None
    )

    if for_clause:
        _lower_go_for_clause(ctx, for_clause, body_node, node)
    elif range_clause:
        _lower_go_range(ctx, range_clause, body_node, node)
    else:
        # Bare for (condition-only or infinite loop)
        _lower_go_bare_for(ctx, node, body_node)


def _lower_go_for_clause(ctx: TreeSitterEmitContext, clause, body_node, parent) -> None:
    """Lower a Go C-style for clause (init; cond; update).

    When ``ctx.block_scoped`` is True, the entire loop is wrapped in a
    block scope so that variables declared in the init (e.g.
    ``for i := 0; ...``) are scoped to the loop.
    """
    scope_entered = ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()

    init_node = clause.child_by_field_name("initializer")
    cond_node = clause.child_by_field_name(ctx.constants.for_condition_field)
    update_node = clause.child_by_field_name(ctx.constants.for_update_field)

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
        ctx.lower_stmt(update_node)
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    if scope_entered:
        ctx.exit_block_scope()


def _lower_go_range(ctx: TreeSitterEmitContext, clause, body_node, parent) -> None:
    # for k, v := range expr { body }
    left = clause.child_by_field_name(ctx.constants.assign_left_field)
    right = clause.child_by_field_name(ctx.constants.assign_right_field)

    iter_reg = ctx.lower_expr(right) if right else ctx.fresh_reg()
    raw_names = extract_expression_list(ctx, left) if left else ["__range_var"]

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("range_cond")
    body_label = ctx.fresh_label("range_body")
    end_label = ctx.fresh_label("range_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.enter_block_scope()
    var_names = [ctx.declare_block_var(n) for n in raw_names]
    # Store index variable
    if len(var_names) >= 1:
        ctx.emit(Opcode.STORE_VAR, operands=[var_names[0], idx_reg])
    # Store value variable
    if len(var_names) >= 2:
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[iter_reg, idx_reg],
        )
        ctx.emit(Opcode.STORE_VAR, operands=[var_names[1], elem_reg])

    update_label = ctx.fresh_label("range_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _lower_go_bare_for(ctx: TreeSitterEmitContext, node, body_node) -> None:
    """Bare for loop: `for { ... }` or `for cond { ... }`."""
    # Check if there is a condition child (not for_clause/range_clause/block/for)
    cond_node = next(
        (
            c
            for c in node.children
            if c.is_named
            and c.type
            not in (
                GoNodeType.FOR_CLAUSE,
                GoNodeType.RANGE_CLAUSE,
                GoNodeType.BLOCK,
                GoNodeType.FOR,
            )
        ),
        None,
    )

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
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# -- Go: inc/dec statements ------------------------------------------------


def lower_go_inc(ctx: TreeSitterEmitContext, node) -> None:
    children = [c for c in node.children if c.is_named]
    if not children:
        return
    operand = children[0]
    operand_reg = ctx.lower_expr(operand)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result_reg,
        operands=["+", operand_reg, one_reg],
        node=node,
    )
    lower_go_store_target(ctx, operand, result_reg, node)


def lower_go_dec(ctx: TreeSitterEmitContext, node) -> None:
    children = [c for c in node.children if c.is_named]
    if not children:
        return
    operand = children[0]
    operand_reg = ctx.lower_expr(operand)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result_reg,
        operands=["-", operand_reg, one_reg],
        node=node,
    )
    lower_go_store_target(ctx, operand, result_reg, node)


# -- Go: return statement --------------------------------------------------


def lower_go_return(ctx: TreeSitterEmitContext, node) -> None:
    children = [c for c in node.children if c.type != GoNodeType.RETURN and c.is_named]
    if not children:
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
        return
    # If expression_list, lower each value
    if len(children) == 1 and children[0].type == GoNodeType.EXPRESSION_LIST:
        regs = lower_expression_list(ctx, children[0])
    else:
        regs = [ctx.lower_expr(c) for c in children]
    for reg in regs:
        ctx.emit(
            Opcode.RETURN,
            operands=[reg],
            node=node,
        )


# -- Go: defer statement ---------------------------------------------------


def lower_defer_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower defer statement: lower call child, then CALL_FUNCTION('defer', call_reg)."""
    call_node = next(
        (c for c in node.children if c.is_named and c.type != GoNodeType.DEFER),
        None,
    )
    if not call_node:
        return
    call_reg = ctx.lower_expr(call_node)
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=ctx.fresh_reg(),
        operands=["defer", call_reg],
        node=node,
    )


# -- Go: go statement ------------------------------------------------------


def lower_go_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower go statement: lower call child, then CALL_FUNCTION('go', call_reg)."""
    call_node = next(
        (c for c in node.children if c.is_named and c.type != GoNodeType.GO),
        None,
    )
    if not call_node:
        return
    call_reg = ctx.lower_expr(call_node)
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=ctx.fresh_reg(),
        operands=["go", call_reg],
        node=node,
    )


# -- Go: expression switch statement ---------------------------------------


def lower_expression_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower expression_switch_statement as if/else chain.

    Go allows ``switch x := expr; x { }``.  The init variable is scoped
    to the switch body.
    """
    init_node = node.child_by_field_name("initializer")
    scope_entered = init_node is not None and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()
    if init_node:
        ctx.lower_stmt(init_node)

    value_node = node.child_by_field_name("value")
    val_reg = (
        ctx.lower_expr(value_node)
        if value_node
        else _make_const_val(ctx, ctx.constants.true_literal)
    )

    end_label = ctx.fresh_label("switch_end")
    cases = [
        c
        for c in node.children
        if c.type in (GoNodeType.EXPRESSION_CASE, GoNodeType.DEFAULT_CASE)
    ]

    ctx.push_loop(end_label, end_label)
    for case in cases:
        if case.type == GoNodeType.DEFAULT_CASE:
            body_children = [c for c in case.children if c.is_named]
            for child in body_children:
                ctx.lower_stmt(child)
            ctx.emit(Opcode.BRANCH, label=end_label)
        else:
            value_nodes = [
                c for c in case.children if c.type == GoNodeType.EXPRESSION_LIST
            ]
            body_label = ctx.fresh_label("case_body")
            next_label = ctx.fresh_label("case_next")

            if value_nodes:
                case_exprs = lower_expression_list(ctx, value_nodes[0])
                if case_exprs:
                    cmp_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.BINOP,
                        result_reg=cmp_reg,
                        operands=["==", val_reg, case_exprs[0]],
                        node=case,
                    )
                    ctx.emit(
                        Opcode.BRANCH_IF,
                        operands=[cmp_reg],
                        label=f"{body_label},{next_label}",
                    )
                else:
                    ctx.emit(Opcode.BRANCH, label=body_label)
            else:
                ctx.emit(Opcode.BRANCH, label=body_label)

            ctx.emit(Opcode.LABEL, label=body_label)
            body_children = [
                c
                for c in case.children
                if c.is_named and c.type != GoNodeType.EXPRESSION_LIST
            ]
            for child in body_children:
                ctx.lower_stmt(child)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=next_label)

    ctx.pop_loop()
    ctx.emit(Opcode.LABEL, label=end_label)

    if scope_entered:
        ctx.exit_block_scope()


def _make_const_val(ctx: TreeSitterEmitContext, value: str) -> str:
    """Emit a CONST and return its register."""
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[value])
    return reg


# -- Go: type switch statement ---------------------------------------------


def lower_type_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower type_switch_statement with CALL_FUNCTION('type_check') per case."""
    header = next(
        (c for c in node.children if c.type == GoNodeType.TYPE_SWITCH_HEADER), None
    )
    expr_reg = ctx.fresh_reg()
    if header:
        named = [c for c in header.children if c.is_named]
        if named:
            expr_reg = ctx.lower_expr(named[-1])

    end_label = ctx.fresh_label("type_switch_end")
    cases = [
        c
        for c in node.children
        if c.type in (GoNodeType.TYPE_CASE, GoNodeType.DEFAULT_CASE)
    ]

    ctx.push_loop(end_label, end_label)
    for case in cases:
        if case.type == GoNodeType.DEFAULT_CASE:
            body_children = [c for c in case.children if c.is_named]
            for child in body_children:
                ctx.lower_stmt(child)
            ctx.emit(Opcode.BRANCH, label=end_label)
        else:
            type_nodes = [
                c
                for c in case.children
                if c.type not in (GoNodeType.CASE, GoNodeType.COLON) and c.is_named
            ]
            body_label = ctx.fresh_label("type_case_body")
            next_label = ctx.fresh_label("type_case_next")

            if type_nodes:
                type_text = ctx.node_text(type_nodes[0])
                check_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=check_reg,
                    operands=["type_check", expr_reg, type_text],
                    node=case,
                )
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[check_reg],
                    label=f"{body_label},{next_label}",
                )
            else:
                ctx.emit(Opcode.BRANCH, label=body_label)

            ctx.emit(Opcode.LABEL, label=body_label)
            body_children = type_nodes[1:] if len(type_nodes) > 1 else []
            for child in body_children:
                ctx.lower_stmt(child)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=next_label)

    ctx.pop_loop()
    ctx.emit(Opcode.LABEL, label=end_label)


# -- Go: select statement --------------------------------------------------


def lower_select_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower select_statement: lower each communication_case."""
    end_label = ctx.fresh_label("select_end")
    cases = [
        c
        for c in node.children
        if c.type in (GoNodeType.COMMUNICATION_CASE, GoNodeType.DEFAULT_CASE)
    ]

    for case in cases:
        case_label = ctx.fresh_label("select_case")
        ctx.emit(Opcode.LABEL, label=case_label)
        body_children = [c for c in case.children if c.is_named]
        for child in body_children:
            ctx.lower_stmt(child)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# -- Go: send statement ----------------------------------------------------


def lower_send_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower send_statement: ch <- val -> CALL_FUNCTION('chan_send', ch, val)."""
    channel_node = node.child_by_field_name("channel")
    value_node = node.child_by_field_name("value")
    if not channel_node or not value_node:
        named = [c for c in node.children if c.is_named]
        channel_node = named[0] if named else None
        value_node = named[-1] if len(named) > 1 else None

    chan_reg = ctx.lower_expr(channel_node) if channel_node else ctx.fresh_reg()
    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=ctx.fresh_reg(),
        operands=["chan_send", chan_reg, val_reg],
        node=node,
    )


# -- Go: labeled statement -------------------------------------------------


def lower_labeled_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower labeled_statement: LABEL(name) + lower body."""
    label_node = next(
        (c for c in node.children if c.type == GoNodeType.LABEL_NAME),
        None,
    )
    label_name = ctx.node_text(label_node) if label_node else "__label"
    ctx.emit(Opcode.LABEL, label=label_name)
    body_children = [
        c for c in node.children if c.is_named and c.type != GoNodeType.LABEL_NAME
    ]
    for child in body_children:
        ctx.lower_stmt(child)


# -- Go: goto statement ----------------------------------------------------


def lower_goto_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto_statement as BRANCH(label_name)."""
    label_node = next(
        (c for c in node.children if c.type == GoNodeType.LABEL_NAME),
        None,
    )
    label_name = ctx.node_text(label_node) if label_node else "__unknown_label"
    ctx.emit(
        Opcode.BRANCH,
        label=label_name,
        node=node,
    )


# -- Go: receive statement -------------------------------------------------


def lower_receive_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower receive_statement: v := <-ch -> CALL_FUNCTION('chan_recv', ch) + STORE_VAR."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)

    if right:
        chan_reg = ctx.lower_expr(right)
    else:
        # Bare receive -- find the unary_expression child (<-ch)
        unary = next(
            (c for c in node.children if c.type == GoNodeType.UNARY_EXPRESSION),
            None,
        )
        chan_reg = ctx.lower_expr(unary) if unary else ctx.fresh_reg()

    recv_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=recv_reg,
        operands=["chan_recv", chan_reg],
        node=node,
    )

    if left:
        left_names = extract_expression_list(ctx, left)
        for name in left_names:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[name, recv_reg],
                node=node,
            )
