"""Lua-specific declaration and assignment lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.declarations import lower_params

logger = logging.getLogger(__name__)


def lower_lua_variable_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `local x = expr` -- variable_declaration wraps assignment_statement."""
    for child in node.children:
        if child.type == "assignment_statement":
            lower_lua_assignment(ctx, child)
            return
    # Local declaration without assignment: local x
    for child in node.children:
        if child.type == "identifier":
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(child), val_reg],
                node=node,
            )


def lower_lua_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assignment_statement with variable_list and expression_list."""
    var_list_node = next((c for c in node.children if c.type == "variable_list"), None)
    expr_list_node = next(
        (c for c in node.children if c.type == "expression_list"), None
    )

    if var_list_node is None or expr_list_node is None:
        # Fallback: try positional named children
        named = [c for c in node.children if c.is_named]
        if len(named) >= 2:
            var_list_node, expr_list_node = named[0], named[1]
        else:
            logger.warning(
                "Lua assignment missing variable_list or expression_list at %s",
                ctx.source_loc(node),
            )
            return

    targets = [c for c in var_list_node.children if c.is_named]
    values = [c for c in expr_list_node.children if c.is_named]

    val_regs = [ctx.lower_expr(v) for v in values]

    for i, target in enumerate(targets):
        val_reg = val_regs[i] if i < len(val_regs) else ctx.fresh_reg()
        if i >= len(val_regs):
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
        lower_lua_store_target(ctx, target, val_reg, node)


def lower_lua_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Lua-specific store target supporting dot_index and bracket_index."""
    if target.type == "identifier":
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == "dot_index_expression":
        obj_node = target.child_by_field_name("table")
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == "bracket_index_expression":
        obj_node = target.child_by_field_name("table")
        idx_node = target.child_by_field_name("field")
        if obj_node and idx_node:
            obj_reg = ctx.lower_expr(obj_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


def lower_lua_function_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration with name, parameters, body fields."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_lua_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower return statement."""
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
