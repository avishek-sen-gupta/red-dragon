"""Lua-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args,
    lower_const_literal,
)
from interpreter.frontends.lua.node_types import LuaNodeType

logger = logging.getLogger(__name__)


def lower_lua_call(ctx: TreeSitterEmitContext, node) -> str:
    """Lower function_call -- name field is identifier or method_index_expression."""
    name_node = node.child_by_field_name("name")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args(ctx, args_node) if args_node else []

    if name_node is None:
        target_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=target_reg,
            operands=["unknown_call_target"],
        )
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            node=node,
        )
        return reg

    # Method call: obj:method(args)
    if name_node.type == LuaNodeType.METHOD_INDEX_EXPRESSION:
        table_node = name_node.child_by_field_name("table")
        method_node = name_node.child_by_field_name("method")
        if table_node and method_node:
            obj_reg = ctx.lower_expr(table_node)
            method_name = ctx.node_text(method_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg

    # Dot-indexed call: obj.field(args) — field access + function call
    if name_node.type == LuaNodeType.DOT_INDEX_EXPRESSION:
        table_node = name_node.child_by_field_name("table")
        field_node = name_node.child_by_field_name("field")
        if table_node and field_node:
            obj_reg = ctx.lower_expr(table_node)
            field_name = ctx.node_text(field_node)
            func_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_FIELD,
                result_reg=func_reg,
                operands=[obj_reg, field_name],
                node=node,
            )
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_UNKNOWN,
                result_reg=reg,
                operands=[func_reg] + arg_regs,
                node=node,
            )
            return reg

    # Plain function call
    if name_node.type == LuaNodeType.IDENTIFIER:
        func_name = ctx.node_text(name_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

    # Dynamic call target
    target_reg = ctx.lower_expr(name_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


def lower_dot_index(ctx: TreeSitterEmitContext, node) -> str:
    """Lower dot_index_expression (obj.field)."""
    table_node = node.child_by_field_name("table")
    field_node = node.child_by_field_name("field")
    if table_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(table_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_method_index(ctx: TreeSitterEmitContext, node) -> str:
    """Lower method_index_expression (obj:method) as attribute load.

    When used standalone (not as the callee inside function_call),
    this is equivalent to loading the method attribute from the object.
    """
    table_node = node.child_by_field_name("table")
    method_node = node.child_by_field_name("method")
    if table_node is None or method_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(table_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, method_name],
        node=node,
    )
    return reg


def lower_bracket_index(ctx: TreeSitterEmitContext, node) -> str:
    """Lower bracket_index_expression (obj[key])."""
    table_node = node.child_by_field_name("table")
    key_node = node.child_by_field_name("field")
    if table_node is None or key_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(table_node)
    key_reg = ctx.lower_expr(key_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, key_reg],
        node=node,
    )
    return reg


def lower_table_constructor(ctx: TreeSitterEmitContext, node) -> str:
    """Lower table_constructor ({key=val, ...})."""
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["table"],
        node=node,
    )
    positional_idx = 1
    for child in node.children:
        if child.type == LuaNodeType.FIELD:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                key_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=key_reg,
                    operands=[ctx.node_text(name_node)],
                )
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, key_reg, val_reg],
                )
            elif value_node:
                # Positional entry (array-like)
                idx_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=idx_reg,
                    operands=[str(positional_idx)],
                )
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                )
                positional_idx += 1
    return obj_reg


def lower_expression_list(ctx: TreeSitterEmitContext, node) -> str:
    """Unwrap expression_list to its first named child."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.default_return_value],
    )
    return reg


def lower_lua_function_definition(ctx: TreeSitterEmitContext, node) -> str:
    """Lower function_definition (anonymous function expression).

    Produces BRANCH past body, LABEL, params, body, default RETURN,
    end LABEL, and returns a register holding the func ref.
    """
    from interpreter.frontends.common.declarations import lower_params

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    anon_name = ctx.fresh_label("anon_fn")
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{anon_name}")
    end_label = ctx.fresh_label(f"end_{anon_name}")

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
    ctx.emit_func_ref(anon_name, func_label, result_reg=func_reg)
    return func_reg


def lower_lua_vararg(ctx: TreeSitterEmitContext, node) -> str:
    """Lower vararg_expression (...) as SYMBOLIC('varargs')."""
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=reg,
        operands=["varargs"],
        node=node,
    )
    return reg
