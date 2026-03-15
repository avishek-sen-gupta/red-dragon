"""C++-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_const_literal,
    lower_identifier,
    lower_canonical_none,
)
from interpreter.frontends.c.expressions import lower_c_store_target
from interpreter.frontends.cpp.node_types import CppNodeType
from interpreter.type_expr import ScalarType


def lower_new_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower new T(args) as CALL_FUNCTION."""
    type_node = node.child_by_field_name("type")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    type_name = ctx.node_text(type_node) if type_node else "Object"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[type_name] + arg_regs,
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(type_name))
    return reg


def lower_delete_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower delete ptr as CALL_FUNCTION delete(ptr_reg)."""
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["delete", ptr_reg],
        node=node,
    )
    return reg


def lower_lambda(ctx: TreeSitterEmitContext, node) -> str:
    """Lower lambda_expression like an arrow function."""
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    params_node = node.child_by_field_name("declarator")

    from interpreter.frontends.c.declarations import lower_c_params

    func_name = "__lambda"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        param_list = next(
            (c for c in params_node.children if c.type == CppNodeType.PARAMETER_LIST),
            params_node,
        )
        lower_c_params(ctx, param_list)

    if body_node:
        if body_node.type == CppNodeType.COMPOUND_STATEMENT:
            ctx.lower_block(body_node)
        else:
            val_reg = ctx.lower_expr(body_node)
            ctx.emit(Opcode.RETURN, operands=[val_reg])

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
    return func_reg


def lower_qualified_id(ctx: TreeSitterEmitContext, node) -> str:
    """Lower qualified_identifier (e.g., std::cout) as LOAD_VAR."""
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=reg,
        operands=[ctx.node_text(node)],
        node=node,
    )
    return reg


def lower_throw_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower throw as an expression (C++ throw can appear in expressions)."""
    children = [
        c for c in node.children if c.type != CppNodeType.THROW_KEYWORD and c.is_named
    ]
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
        Opcode.THROW,
        operands=[val_reg],
        node=node,
    )
    return val_reg


def lower_cpp_cast(ctx: TreeSitterEmitContext, node) -> str:
    """Lower static_cast<T>(expr) etc. — pass through the value."""
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_condition_clause(ctx: TreeSitterEmitContext, node) -> str:
    """Unwrap condition_clause to reach the inner expression.

    Skips init_statement children (handled by the enclosing if/while lowerer).
    """
    for child in node.children:
        if (
            child.is_named
            and child.type not in ("(", ")")
            and child.type != CppNodeType.INIT_STATEMENT
        ):
            return ctx.lower_expr(child)
    return lower_const_literal(ctx, node)


def lower_cpp_subscript_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower subscript_expression — C++ wraps index in subscript_argument_list."""
    arr_node = node.child_by_field_name("argument")
    idx_node = node.child_by_field_name("index")
    if arr_node and idx_node:
        # Standard C-style subscript
        from interpreter.frontends.c.expressions import lower_subscript_expr

        return lower_subscript_expr(ctx, node)
    # C++ tree-sitter: first named child = object, subscript_argument_list = index wrapper
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named_children[0])
    suffix = next(
        (c for c in node.children if c.type == CppNodeType.SUBSCRIPT_ARGUMENT_LIST),
        None,
    )
    if suffix:
        idx_children = [c for c in suffix.children if c.is_named]
        idx_reg = ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
    else:
        idx_reg = ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def lower_cpp_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower assignment_expression with C++ subscript support."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_cpp_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_cpp_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Override C store target to handle C++ subscript_expression with subscript_argument_list."""
    if target.type == CppNodeType.SUBSCRIPT_EXPRESSION:
        arr_node = target.child_by_field_name("argument")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            lower_c_store_target(ctx, target, val_reg, parent_node)
            return
        named_children = [c for c in target.children if c.is_named]
        if not named_children:
            lower_c_store_target(ctx, target, val_reg, parent_node)
            return
        obj_reg = ctx.lower_expr(named_children[0])
        suffix = next(
            (
                c
                for c in target.children
                if c.type == CppNodeType.SUBSCRIPT_ARGUMENT_LIST
            ),
            None,
        )
        if suffix:
            idx_children = [c for c in suffix.children if c.is_named]
            idx_reg = (
                ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
            )
        else:
            idx_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.STORE_INDEX,
            operands=[obj_reg, idx_reg, val_reg],
            node=parent_node,
        )
    else:
        lower_c_store_target(ctx, target, val_reg, parent_node)
