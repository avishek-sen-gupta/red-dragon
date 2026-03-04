"""PHP-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext

logger = logging.getLogger(__name__)


def lower_php_compound(ctx: TreeSitterEmitContext, node) -> None:
    """Lower compound_statement (block with braces)."""
    for child in node.children:
        if child.type not in ("{", "}") and child.is_named:
            ctx.lower_stmt(child)


def lower_php_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower return statement with PHP-specific filtering."""
    children = [c for c in node.children if c.type != "return" and c.is_named]
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


def lower_php_echo(ctx: TreeSitterEmitContext, node) -> None:
    """Lower echo statement as CALL_FUNCTION('echo', args)."""
    children = [c for c in node.children if c.type != "echo" and c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in children]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["echo"] + arg_regs,
        node=node,
    )


def lower_php_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower PHP if statement with else_clause / else_if_clause support."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    end_label = ctx.fresh_label("if_end")

    # Collect else_clause children
    else_clauses = [
        c for c in node.children if c.type in ("else_clause", "else_if_clause")
    ]

    if else_clauses:
        false_label = ctx.fresh_label("if_false")
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
        lower_php_compound(ctx, body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if else_clauses:
        ctx.emit(Opcode.LABEL, label=false_label)
        for clause in else_clauses:
            _lower_php_else_clause(ctx, clause, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _lower_php_else_clause(ctx: TreeSitterEmitContext, node, end_label: str) -> None:
    """Lower else_if_clause or else_clause."""
    if node.type == "else_if_clause":
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")
        cond_reg = ctx.lower_expr(cond_node)
        true_label = ctx.fresh_label("elseif_true")
        false_label = ctx.fresh_label("elseif_false")

        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            node=node,
        )

        ctx.emit(Opcode.LABEL, label=true_label)
        if body_node:
            lower_php_compound(ctx, body_node)
        ctx.emit(Opcode.BRANCH, label=end_label)

        ctx.emit(Opcode.LABEL, label=false_label)
    elif node.type == "else_clause":
        for child in node.children:
            if child.type not in ("else", "{", "}") and child.is_named:
                if child.type == "compound_statement":
                    lower_php_compound(ctx, child)
                else:
                    ctx.lower_stmt(child)


def lower_php_foreach(ctx: TreeSitterEmitContext, node) -> None:
    """Lower foreach ($arr as $v) or foreach ($arr as $k => $v) as index-based loop."""
    body_node = node.child_by_field_name("body")

    # Extract iterable, value var, and optional key var from children
    named_children = [c for c in node.children if c.is_named]
    iterable_node = named_children[0] if named_children else None
    binding_node = named_children[1] if len(named_children) > 1 else None

    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()

    key_var = None
    value_var = None
    if binding_node and binding_node.type == "pair":
        # $k => $v
        pair_named = [c for c in binding_node.children if c.is_named]
        key_var = ctx.node_text(pair_named[0]) if pair_named else None
        value_var = ctx.node_text(pair_named[1]) if len(pair_named) > 1 else None
    elif binding_node:
        value_var = ctx.node_text(binding_node)

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("foreach_cond")
    body_label = ctx.fresh_label("foreach_body")
    end_label = ctx.fresh_label("foreach_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    # Store key variable (index) if present
    if key_var:
        ctx.emit(Opcode.STORE_VAR, operands=[key_var, idx_reg])
    # Store value variable (element at index)
    if value_var:
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[iter_reg, idx_reg],
        )
        ctx.emit(Opcode.STORE_VAR, operands=[value_var, elem_reg])

    update_label = ctx.fresh_label("foreach_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__foreach_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_php_throw(ctx: TreeSitterEmitContext, node) -> None:
    """Lower throw statement."""
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_php_try(ctx: TreeSitterEmitContext, node) -> None:
    """Lower try/catch/finally."""
    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    for child in node.children:
        if child.type == "catch_clause":
            # PHP catch_clause: type(s) and variable_name
            type_node = next(
                (
                    c
                    for c in child.children
                    if c.type in ("named_type", "name", "qualified_name")
                ),
                None,
            )
            var_node = next(
                (c for c in child.children if c.type == "variable_name"),
                None,
            )
            exc_type = ctx.node_text(type_node) if type_node else None
            exc_var = ctx.node_text(var_node) if var_node else None
            catch_body = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == "compound_statement"),
                None,
            )
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == "finally_clause":
            finally_node = next(
                (c for c in child.children if c.type == "compound_statement"),
                None,
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def lower_php_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch(expr) { case ... } as an if/else chain."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    cases = (
        [
            c
            for c in body_node.children
            if c.type in ("case_statement", "default_statement")
        ]
        if body_node
        else []
    )

    for case in cases:
        is_default = case.type == "default_statement"
        value_node = case.child_by_field_name("value")
        body_stmts = [c for c in case.children if c.is_named and c != value_node]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if not is_default and value_node:
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
                label=f"{arm_label},{next_label}",
            )
        else:
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_php_do(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (condition);"""
    body_node = node.child_by_field_name("body")
    cond_node = node.child_by_field_name("condition")

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
            label=f"{body_label},{end_label}",
            node=node,
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_php_namespace(ctx: TreeSitterEmitContext, node) -> None:
    """Lower namespace definition: just lower the body compound_statement."""
    body_node = next((c for c in node.children if c.type == "compound_statement"), None)
    if body_node:
        lower_php_compound(ctx, body_node)


def lower_php_named_label(ctx: TreeSitterEmitContext, node) -> None:
    """Lower name: as LABEL user_{name}."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        name_node = next((c for c in node.children if c.type == "name"), None)
    if name_node:
        label_name = f"user_{ctx.node_text(name_node)}"
        ctx.emit(
            Opcode.LABEL,
            label=label_name,
            node=node,
        )
    else:
        logger.warning(
            "named_label_statement without name: %s", ctx.node_text(node)[:40]
        )


def lower_php_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto name; as BRANCH user_{name}."""
    name_node = node.child_by_field_name("label")
    if not name_node:
        name_node = next((c for c in node.children if c.type == "name"), None)
    if name_node:
        target_label = f"user_{ctx.node_text(name_node)}"
        ctx.emit(
            Opcode.BRANCH,
            label=target_label,
            node=node,
        )
    else:
        logger.warning("goto_statement without label: %s", ctx.node_text(node)[:40])
