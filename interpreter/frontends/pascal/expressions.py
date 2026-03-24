"""Pascal-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.frontends.common.expressions import lower_const_literal
from interpreter.frontends.common.property_accessors import emit_field_load_or_getter
from interpreter.frontends.pascal.pascal_constants import (
    K_OPERATOR_MAP,
    K_UNARY_MAP,
    KEYWORD_NOISE,
)
from interpreter.frontends.pascal.node_types import PascalNodeType
from interpreter.frontends.pascal.declarations import _resolve_object_class
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_pascal_binop(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprBinary -- children: lhs, operator_keyword, rhs."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)

    # Find the operator keyword between operands
    op_symbol = "?"
    lhs_node = named_children[0]
    rhs_node = named_children[-1]

    for child in node.children:
        mapped = K_OPERATOR_MAP.get(child.type)
        if mapped:
            op_symbol = mapped
            break

    # Fallback: if no k-prefixed operator found, use text of middle child
    if op_symbol == "?" and len(named_children) >= 3:
        op_symbol = ctx.node_text(named_children[1])

    lhs_reg = ctx.lower_expr(lhs_node)
    rhs_reg = ctx.lower_expr(rhs_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=reg,
        operands=[op_symbol, lhs_reg, rhs_reg],
        node=node,
    )
    return reg


def lower_pascal_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprCall -- children: identifier, (, exprArgs, )."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    args_node = next(
        (c for c in node.children if c.type == PascalNodeType.EXPR_ARGS), None
    )
    arg_regs = _extract_pascal_args(ctx, args_node)

    if id_node:
        func_name = ctx.node_text(id_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

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


def _extract_pascal_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract argument registers from exprArgs node."""
    if args_node is None:
        return []
    return [
        ctx.lower_expr(c)
        for c in args_node.children
        if c.is_named and c.type not in KEYWORD_NOISE
    ]


def lower_pascal_paren(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprParens -- unwrap inner expression."""
    inner = next(
        (c for c in node.children if c.type not in ("(", ")")),
        None,
    )
    if inner is None:
        return lower_const_literal(ctx, node)
    return ctx.lower_expr(inner)


def lower_pascal_dot(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprDot -- first child = object, last child = field name.

    If the object is a class-typed variable with a registered property getter,
    emit CALL_METHOD __get_<field>__ instead of plain LOAD_FIELD.
    """
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)
    obj_node = named_children[0]
    field_node = named_children[-1]
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)

    # Check if obj is a class-typed variable for property interception
    obj_class = _resolve_object_class(ctx, obj_node)
    if obj_class:
        return emit_field_load_or_getter(ctx, obj_reg, obj_class, field_name, node)

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_pascal_subscript(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprSubscript -- object followed by exprArgs containing index."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if not named_children:
        return lower_const_literal(ctx, node)
    obj_node = named_children[0]
    args_node = next(
        (c for c in node.children if c.type == PascalNodeType.EXPR_ARGS), None
    )
    obj_reg = ctx.lower_expr(obj_node)
    if args_node:
        idx_children = [
            c for c in args_node.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        if idx_children:
            idx_reg = ctx.lower_expr(idx_children[0])
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_INDEX,
                result_reg=reg,
                operands=[obj_reg, idx_reg],
                node=node,
            )
            return reg
    return obj_reg


def lower_pascal_unary(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprUnary -- operator keyword + operand."""
    op_symbol = "?"
    for child in node.children:
        mapped = K_UNARY_MAP.get(child.type)
        if mapped:
            op_symbol = mapped
            break
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if not named_children:
        return lower_const_literal(ctx, node)
    operand_reg = ctx.lower_expr(named_children[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=[op_symbol, operand_reg],
        node=node,
    )
    return reg


def lower_pascal_brackets(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower exprBrackets (set literal) as NEW_ARRAY + STORE_INDEX per element."""
    elems = [c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["set", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


def lower_pascal_range(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `4..10` as CALL_FUNCTION('range', lo, hi)."""
    nums = [c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE]
    arg_regs = [ctx.lower_expr(c) for c in nums]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["range"] + arg_regs,
        node=node,
    )
    return reg


def lower_pascal_inherited_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `inherited Create` as CALL_FUNCTION('inherited', method)."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if named_children:
        method_name = ctx.node_text(named_children[0])
    else:
        method_name = "inherited"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["inherited", method_name],
        node=node,
    )
    return reg
