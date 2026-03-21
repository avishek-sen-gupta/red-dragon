"""Lua-specific declaration and assignment lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.declarations import lower_params
from interpreter.frontends.lua.node_types import LuaNodeType

logger = logging.getLogger(__name__)


def lower_lua_variable_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `local x = expr` -- variable_declaration wraps assignment_statement."""
    for child in node.children:
        if child.type == LuaNodeType.ASSIGNMENT_STATEMENT:
            lower_lua_assignment(ctx, child)
            return
    # Local declaration without assignment: local x
    for child in node.children:
        if child.type == LuaNodeType.IDENTIFIER:
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[ctx.node_text(child), val_reg],
                node=node,
            )


def lower_lua_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assignment_statement with variable_list and expression_list."""
    var_list_node = next(
        (c for c in node.children if c.type == LuaNodeType.VARIABLE_LIST), None
    )
    expr_list_node = next(
        (c for c in node.children if c.type == LuaNodeType.EXPRESSION_LIST), None
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
    if target.type == LuaNodeType.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == LuaNodeType.DOT_INDEX_EXPRESSION:
        obj_node = target.child_by_field_name("table")
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == LuaNodeType.BRACKET_INDEX_EXPRESSION:
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
    """Lower function_declaration with name, parameters, body fields.

    For dotted names (``function Counter.new()``), the function is stored
    as a field on the table object via STORE_FIELD rather than as a
    top-level variable.  The function name used in labels and func refs
    is just the method name (``new``), not the dotted path.
    """
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    is_dotted = (
        name_node is not None and name_node.type == LuaNodeType.DOT_INDEX_EXPRESSION
    )
    if is_dotted:
        table_node = name_node.child_by_field_name("table")
        field_node = name_node.child_by_field_name("field")
        table_name = ctx.node_text(table_node) if table_node else ""
        func_name = ctx.node_text(field_node) if field_node else "__anon"
    else:
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
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)

    if is_dotted and table_name:
        obj_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=obj_reg, operands=[table_name])
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[obj_reg, func_name, func_reg],
            node=node,
        )
    else:
        ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_lua_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower return statement."""
    children = [c for c in node.children if c.type != LuaNodeType.RETURN and c.is_named]
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


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------
# Lua uses table-based OOP with no fixed class syntax; extraction is not
# straightforward without heuristic analysis. Return an empty SymbolTable.


def extract_lua_symbols(root) -> "SymbolTable":
    """Return an empty SymbolTable — Lua table-based OOP has no extractable class syntax."""
    from interpreter.frontends.symbol_table import SymbolTable

    return SymbolTable.empty()
