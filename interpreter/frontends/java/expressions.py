"""Java-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_const_literal,
    lower_store_target,
)
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.java.node_types import JavaNodeType
from interpreter.type_expr import ScalarType


def lower_method_invocation(ctx: TreeSitterEmitContext, node) -> str:
    name_node = node.child_by_field_name("name")
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    if obj_node:
        obj_reg = ctx.lower_expr(obj_node)
        method_name = ctx.node_text(name_node) if name_node else "unknown"
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=reg,
            operands=[obj_reg, method_name] + arg_regs,
            node=node,
        )
        return reg

    func_name = ctx.node_text(name_node) if name_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[func_name] + arg_regs,
        node=node,
    )
    return reg


def lower_object_creation(ctx: TreeSitterEmitContext, node) -> str:
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


def lower_field_access(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    field_node = node.child_by_field_name("field")
    if obj_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_method_reference(ctx: TreeSitterEmitContext, node) -> str:
    """Lower method_reference: Type::method or obj::method or Type::new."""
    obj_node = node.children[0]
    method_node = node.children[-1]
    obj_reg = ctx.lower_expr(obj_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, method_name],
        node=node,
    )
    return reg


def lower_scoped_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower scoped_identifier (e.g., java.lang.System) as LOAD_VAR."""
    qualified_name = ctx.node_text(node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=reg,
        operands=[qualified_name],
        node=node,
    )
    return reg


def lower_class_literal(ctx: TreeSitterEmitContext, node) -> str:
    """Lower class_literal: Type.class -> LOAD_FIELD(type_reg, 'class')."""
    type_node = node.children[0]
    type_reg = ctx.lower_expr(type_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[type_reg, "class"],
        node=node,
    )
    return reg


def lower_lambda(ctx: TreeSitterEmitContext, node) -> str:
    """Lower lambda_expression: (params) -> expr or (params) -> { body }."""
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}__lambda")
    end_label = ctx.fresh_label("lambda_end")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        _lower_lambda_params(ctx, params_node)

    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node and body_node.type == JavaNodeType.BLOCK:
        ctx.lower_block(body_node)
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    elif body_node:
        body_reg = ctx.lower_expr(body_node)
        ctx.emit(Opcode.RETURN, operands=[body_reg])

    ctx.emit(Opcode.LABEL, label=end_label)

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref("__lambda", func_label, result_reg=ref_reg, node=node)
    return ref_reg


def _lower_lambda_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower parameters for lambda expressions."""
    if params_node.type == JavaNodeType.FORMAL_PARAMETERS:
        lower_java_params(ctx, params_node)
    else:
        for child in params_node.children:
            if child.type == JavaNodeType.IDENTIFIER:
                pname = ctx.node_text(child)
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=ctx.fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )


def lower_array_access(ctx: TreeSitterEmitContext, node) -> str:
    arr_node = node.child_by_field_name("array")
    idx_node = node.child_by_field_name("index")
    if arr_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    arr_reg = ctx.lower_expr(arr_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[arr_reg, idx_reg],
        node=node,
    )
    return reg


def lower_array_creation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower array_creation_expression or standalone array_initializer."""
    # Handle standalone array_initializer: {1, 2, 3}
    if node.type == JavaNodeType.ARRAY_INITIALIZER:
        elements = [c for c in node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
        arr_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            val_reg = ctx.lower_expr(elem)
            ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # array_creation_expression: look for array_initializer child
    init_node = next(
        (c for c in node.children if c.type == JavaNodeType.ARRAY_INITIALIZER),
        None,
    )
    if init_node is not None:
        elements = [c for c in init_node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
        arr_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            val_reg = ctx.lower_expr(elem)
            ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # Sized array without initializer: new int[5]
    dims_node = next(
        (c for c in node.children if c.type == JavaNodeType.DIMENSIONS_EXPR),
        None,
    )
    if dims_node:
        dim_children = [c for c in dims_node.children if c.is_named]
        size_reg = ctx.lower_expr(dim_children[0]) if dim_children else ctx.fresh_reg()
    else:
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
    arr_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["array", size_reg],
        node=node,
    )
    return arr_reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_java_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_java_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == JavaNodeType.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == JavaNodeType.FIELD_ACCESS:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == JavaNodeType.ARRAY_ACCESS:
        arr_node = target.child_by_field_name("array")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            arr_reg = ctx.lower_expr(arr_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[arr_reg, idx_reg, val_reg],
                node=parent_node,
            )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


def lower_cast_expr(ctx: TreeSitterEmitContext, node) -> str:
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_instanceof(ctx: TreeSitterEmitContext, node) -> str:
    """Lower instanceof_expression: operand instanceof Type."""
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    type_node = named_children[1] if len(named_children) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["instanceof", obj_reg, type_reg],
        node=node,
    )
    return reg


def lower_ternary(ctx: TreeSitterEmitContext, node) -> str:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
    )
    ctx.emit(Opcode.LABEL, label=true_label)
    true_reg = ctx.lower_expr(true_node)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=false_label)
    false_reg = ctx.lower_expr(false_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    result_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
    return result_reg


def lower_expr_stmt_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower expression_statement in expr context (e.g., inside switch expression)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_throw_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower throw_statement in expr context (e.g., switch expression arm)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        val_reg = ctx.lower_expr(named_children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.default_return_value],
        )
    ctx.emit(Opcode.THROW, operands=[val_reg], node=node)
    return val_reg


# ── shared Java param helper (used by expressions + declarations) ─────


def lower_java_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == JavaNodeType.FORMAL_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=param_reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
        elif child.type == JavaNodeType.SPREAD_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=ctx.fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
