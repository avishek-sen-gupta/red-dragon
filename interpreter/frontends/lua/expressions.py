# pyright: standard
"""Lua-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args,
    lower_const_literal,
)
from interpreter.frontends.lua.node_types import LuaNodeType
from interpreter.register import Register
from interpreter.field_name import FieldName
from interpreter.types.type_expr import scalar
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Const,
    LoadField,
    LoadIndex,
    NewObject,
    CallFunction,
    CallMethod,
    CallUnknown,
    Symbolic,
    Label_,
    Branch,
    Return_,
    StoreIndex,
)

logger = logging.getLogger(__name__)


def lower_lua_call(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower function_call -- name field is identifier or method_index_expression."""
    name_node = node.child_by_field_name("name")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args(ctx, args_node) if args_node else []

    if name_node is None:
        target_reg = ctx.fresh_reg()
        ctx.emit_inst(Symbolic(result_reg=target_reg, hint="unknown_call_target"))
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),  # type: ignore[arg-type]  # see red-dragon-hzmm
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
            ctx.emit_inst(
                CallMethod(
                    result_reg=reg,
                    obj_reg=obj_reg,
                    method_name=FuncName(method_name),
                    args=tuple(arg_regs),  # type: ignore[arg-type]  # see red-dragon-hzmm
                ),
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
            ctx.emit_inst(
                LoadField(
                    result_reg=func_reg,
                    obj_reg=obj_reg,
                    field_name=FieldName(field_name),
                ),
                node=node,
            )
            reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallUnknown(result_reg=reg, target_reg=func_reg, args=tuple(arg_regs)),  # type: ignore[arg-type]  # see red-dragon-hzmm
                node=node,
            )
            return reg

    # Plain function call
    if name_node.type == LuaNodeType.IDENTIFIER:
        func_name = ctx.node_text(name_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=reg, func_name=FuncName(func_name), args=tuple(arg_regs)  # type: ignore[arg-type]  # see red-dragon-hzmm
            ),
            node=node,
        )
        return reg

    # Dynamic call target
    target_reg = ctx.lower_expr(name_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),  # type: ignore[arg-type]  # see red-dragon-hzmm
        node=node,
    )
    return reg


def lower_dot_index(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower dot_index_expression (obj.field)."""
    table_node = node.child_by_field_name("table")
    field_node = node.child_by_field_name("field")
    if table_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(table_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_method_index(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(method_name)),
        node=node,
    )
    return reg


def lower_bracket_index(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower bracket_index_expression (obj[key])."""
    table_node = node.child_by_field_name("table")
    key_node = node.child_by_field_name("field")
    if table_node is None or key_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(table_node)
    key_reg = ctx.lower_expr(key_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=key_reg), node=node
    )
    return reg


def lower_table_constructor(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower table_constructor ({key=val, ...})."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar("table")), node=node)
    positional_idx = 1
    for child in node.children:
        if child.type == LuaNodeType.FIELD:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                key_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=key_reg, value=ctx.node_text(name_node)))
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
                )
            elif value_node:
                # Positional entry (array-like)
                idx_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=idx_reg, value=str(positional_idx)))
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg)
                )
                positional_idx += 1
    return obj_reg


def lower_expression_list(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Unwrap expression_list to its first named child."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.default_return_value))
    return reg


def lower_lua_function_definition(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(str(anon_name), func_label, result_reg=func_reg)  # type: ignore[arg-type]  # see red-dragon-1vgf
    return func_reg


def lower_lua_vararg(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower vararg_expression (...) as SYMBOLIC('varargs')."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=reg, hint="varargs"), node=node)
    return reg
