"""C-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.frontends.common.expressions import lower_const_literal
from interpreter.frontends.c.node_types import CNodeType

logger = logging.getLogger(__name__)


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower field_expression (e.g., obj.field or ptr->field)."""
    obj_node = node.child_by_field_name("argument")
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


def lower_subscript_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower subscript_expression (arr[idx])."""
    arr_node = node.child_by_field_name("argument")
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


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower assignment_expression (x = val)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_c_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_c_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """C-specific store target handling (field_expression, subscript, pointer)."""
    if target.type == CNodeType.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == CNodeType.FIELD_EXPRESSION:
        obj_node = target.child_by_field_name("argument")
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == CNodeType.SUBSCRIPT_EXPRESSION:
        arr_node = target.child_by_field_name("argument")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            arr_reg = ctx.lower_expr(arr_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[arr_reg, idx_reg, val_reg],
                node=parent_node,
            )
    elif target.type == CNodeType.POINTER_EXPRESSION:
        # *ptr = val -> lower_expr(ptr_operand) -> STORE_INDIRECT ptr_reg, val_reg
        operand_node = target.child_by_field_name("argument")
        if operand_node is None:
            operand_node = next((c for c in target.children if c.is_named), None)
        ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        ctx.emit(
            Opcode.STORE_INDIRECT,
            operands=[ptr_reg, val_reg],
            node=parent_node,
        )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


def lower_cast_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower cast_expression — pass through the value."""
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_pointer_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower pointer dereference (*p) as LOAD_INDIRECT or address-of (&x) as ADDRESS_OF."""
    operand_node = node.child_by_field_name("argument")
    # Detect operator: first non-named child is '*' or '&'
    op_char = next(
        (
            ctx.node_text(c)
            for c in node.children
            if not c.is_named and ctx.node_text(c) in ("*", "&")
        ),
        "*",
    )
    if operand_node is None:
        operand_node = next((c for c in node.children if c.is_named), None)

    if op_char == "&":
        # For simple identifiers, emit ADDRESS_OF for alias tracking.
        # For complex expressions (field access, array index), fall back to UNOP.
        if operand_node and operand_node.type == CNodeType.IDENTIFIER:
            var_name = ctx.node_text(operand_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.ADDRESS_OF,
                result_reg=reg,
                operands=[var_name],
                node=node,
            )
            return reg
        inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=["&", inner_reg],
            node=node,
        )
        return reg

    # Dereference *this → just load this (our VM references aren't real pointers)
    if operand_node is not None and ctx.node_text(operand_node) == "this":
        return ctx.lower_expr(operand_node)

    # Dereference: *ptr -> LOAD_INDIRECT ptr
    inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDIRECT,
        result_reg=reg,
        operands=[inner_reg],
        node=node,
    )
    return reg


def lower_sizeof(ctx: TreeSitterEmitContext, node) -> str:
    """Lower sizeof(type) or sizeof(expr) as CALL_FUNCTION sizeof(arg)."""
    type_node = next(
        (c for c in node.children if c.type == CNodeType.TYPE_DESCRIPTOR),
        None,
    )
    if type_node:
        arg_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=arg_reg,
            operands=[ctx.node_text(type_node)],
        )
    else:
        expr_node = next(
            (c for c in node.children if c.is_named and c.type != CNodeType.SIZEOF),
            None,
        )
        arg_reg = ctx.lower_expr(expr_node) if expr_node else ctx.fresh_reg()

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["sizeof", arg_reg],
        node=node,
    )
    return reg


def lower_ternary(ctx: TreeSitterEmitContext, node) -> str:
    """Lower conditional_expression (ternary operator)."""
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


def lower_comma_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower comma expression (a, b) — evaluate both, return last."""
    children = [c for c in node.children if c.is_named]
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    for child in children:
        reg = ctx.lower_expr(child)
    return reg


def lower_compound_literal(ctx: TreeSitterEmitContext, node) -> str:
    """Lower (type){elem1, elem2, ...} as NEW_OBJECT + STORE_INDEX per element."""
    type_node = next(
        (c for c in node.children if c.type == CNodeType.TYPE_DESCRIPTOR),
        None,
    )
    init_node = next(
        (c for c in node.children if c.type == CNodeType.INITIALIZER_LIST),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else "compound"
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[type_name],
        node=node,
    )
    if init_node:
        elements = [c for c in init_node.children if c.is_named]
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            val_reg = ctx.lower_expr(elem)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
            )
    return obj_reg


def lower_initializer_list(ctx: TreeSitterEmitContext, node) -> str:
    """Lower initializer_list {a, b, c} as NEW_ARRAY + STORE_INDEX per element."""
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


def lower_initializer_pair(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `.field = value` — lower the value (field binding handled by parent)."""
    value_node = next(
        (
            c
            for c in node.children
            if c.is_named and c.type != CNodeType.FIELD_DESIGNATOR
        ),
        None,
    )
    if value_node:
        return ctx.lower_expr(value_node)
    return lower_const_literal(ctx, node)
