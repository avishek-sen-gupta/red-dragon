"""Kotlin-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.control_flow import lower_break, lower_continue
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.kotlin.expressions import (
    lower_if_expr,
    lower_kotlin_store_target,
)
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT

logger = logging.getLogger(__name__)


# -- assignment --------------------------------------------------------


def lower_kotlin_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name("directly_assignable_expression")
    right = node.child_by_field_name("expression")
    # Fallback: walk children
    if left is None or right is None:
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) >= 2:
            left = named_children[0]
            right = named_children[-1]
        else:
            return
    val_reg = ctx.lower_expr(right)
    lower_kotlin_store_target(ctx, left, val_reg, node)


# -- if statement ------------------------------------------------------


def lower_if_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if as a statement (discard result)."""
    lower_if_expr(ctx, node)


# -- while statement ---------------------------------------------------


def lower_while_stmt(ctx: TreeSitterEmitContext, node) -> None:
    named_children = [c for c in node.children if c.is_named]
    # First named child is condition, last is body
    cond_node = named_children[0] if named_children else None
    body_node = (
        next(
            (c for c in node.children if c.type == KNT.CONTROL_STRUCTURE_BODY),
            None,
        )
        if len(named_children) > 1
        else None
    )

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# -- for statement -----------------------------------------------------


def _find_for_iterable(ctx: TreeSitterEmitContext, node) -> object | None:
    """Find the iterable expression in a for statement (after 'in' keyword)."""
    found_in = False
    for child in node.children:
        if found_in and child.is_named and child.type != KNT.CONTROL_STRUCTURE_BODY:
            return child
        if ctx.node_text(child) == "in":
            found_in = True
    return None


def _extract_for_var_name(ctx: TreeSitterEmitContext, var_node) -> str:
    if var_node.type == KNT.SIMPLE_IDENTIFIER:
        return ctx.node_text(var_node)
    id_node = next(
        (c for c in var_node.children if c.type == KNT.SIMPLE_IDENTIFIER),
        None,
    )
    return ctx.node_text(id_node) if id_node else "__for_var"


def lower_for_stmt(ctx: TreeSitterEmitContext, node) -> None:
    named_children = [c for c in node.children if c.is_named]
    # Typically: variable_declaration, iterable expression, control_structure_body
    var_node = next(
        (
            c
            for c in named_children
            if c.type in (KNT.VARIABLE_DECLARATION, KNT.SIMPLE_IDENTIFIER)
        ),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == KNT.CONTROL_STRUCTURE_BODY),
        None,
    )
    # Iterable is the expression between "in" and body
    iterable_node = _find_for_iterable(ctx, node)

    raw_name = _extract_for_var_name(ctx, var_node) if var_node else "__for_var"
    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

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
    var_name = ctx.declare_block_var(raw_name)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("for_update")
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


# -- jump expression (return, break, continue, throw) ------------------


def lower_jump_expr(ctx: TreeSitterEmitContext, node) -> None:
    text = ctx.node_text(node)
    if text.startswith("return"):
        children = [c for c in node.children if c.type != KNT.RETURN]
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
    elif text.startswith("throw"):
        lower_raise_or_throw(ctx, node, keyword="throw")
    elif text.startswith("break"):
        lower_break(ctx, node)
    elif text.startswith("continue"):
        lower_continue(ctx, node)
    else:
        logger.warning("Unrecognised jump expression: %s", text[:40])


# -- do-while statement ------------------------------------------------


def lower_do_while_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (cond) loop."""
    body_node = next(
        (c for c in node.children if c.type == KNT.CONTROL_STRUCTURE_BODY),
        None,
    )
    # Condition is a named child that's not the body
    cond_node = next(
        (
            c
            for c in node.children
            if c.is_named and c.type != KNT.CONTROL_STRUCTURE_BODY
        ),
        None,
    )

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=cond_label)
    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )
    ctx.emit(Opcode.LABEL, label=end_label)


# -- try/catch/finally -------------------------------------------------


def _extract_try_parts(ctx: TreeSitterEmitContext, node):
    """Extract body, catch clauses, and finally from a try_expression."""
    # First named child that's a statements block is the body
    body_node = next(
        (
            c
            for c in node.children
            if c.type in (KNT.STATEMENTS, KNT.CONTROL_STRUCTURE_BODY)
        ),
        None,
    )
    catch_clauses = []
    finally_node = None
    for child in node.children:
        if child.type == KNT.CATCH_BLOCK:
            # catch_block children: "catch", "(", simple_identifier (var), ":", user_type (type), ")", statements
            ids = [c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER]
            exc_var = ctx.node_text(ids[0]) if ids else None
            type_node = next(
                (c for c in child.children if c.type == KNT.USER_TYPE),
                None,
            )
            exc_type = ctx.node_text(type_node) if type_node else None
            catch_body = next(
                (
                    c
                    for c in child.children
                    if c.type in (KNT.STATEMENTS, KNT.CONTROL_STRUCTURE_BODY)
                ),
                None,
            )
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == KNT.FINALLY_BLOCK:
            finally_node = next(
                (
                    c
                    for c in child.children
                    if c.type in (KNT.STATEMENTS, KNT.CONTROL_STRUCTURE_BODY)
                ),
                None,
            )
    return body_node, catch_clauses, finally_node


def lower_try_stmt(ctx: TreeSitterEmitContext, node) -> None:
    body_node, catch_clauses, finally_node = _extract_try_parts(ctx, node)
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)
