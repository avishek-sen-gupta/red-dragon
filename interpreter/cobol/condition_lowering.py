"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.cobol.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    LiteralNode,
)
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.ir import Opcode

logger = logging.getLogger(__name__)


def lower_condition(
    ctx: EmitContext,
    condition: str,
    layout: DataLayout,
    region_reg: str,
) -> str:
    """Lower a simple condition string to a register holding a boolean.

    Supports: "field OP value" where OP is >, <, >=, <=, =, NOT =
    """
    parts = condition.split()
    if len(parts) >= 3:
        left_name = parts[0]
        if parts[1] == "NOT" and len(parts) >= 4:
            op = "!="
            right_val = parts[3]
        else:
            op_map = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "=": "=="}
            op = op_map.get(parts[1], "==")
            right_val = parts[2]

        if ctx.has_field(left_name, layout):
            left_ref = ctx.resolve_field_ref(left_name, layout, region_reg)
            left_reg = ctx.emit_decode_field(
                region_reg, left_ref.fl, left_ref.offset_reg
            )
        else:
            left_reg = ctx.const_to_reg(ctx.parse_literal(left_name))

        right_parsed = ctx.parse_literal(right_val)
        if isinstance(right_parsed, str) and ctx.has_field(right_parsed, layout):
            right_ref = ctx.resolve_field_ref(right_parsed, layout, region_reg)
            right_reg = ctx.emit_decode_field(
                region_reg, right_ref.fl, right_ref.offset_reg
            )
        else:
            right_reg = ctx.const_to_reg(right_parsed)

        result = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=result,
            operands=[op, left_reg, right_reg],
        )
        return result

    result = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=result, operands=[True])
    return result


def lower_expr_node(
    ctx: EmitContext,
    node: ExprNode,
    layout: DataLayout,
    region_reg: str,
) -> str:
    """Walk an expression tree node and emit IR. Returns result register."""
    if isinstance(node, LiteralNode):
        return ctx.const_to_reg(ctx.parse_literal(node.value))
    if isinstance(node, FieldRefNode):
        if ctx.has_field(node.name, layout):
            ref = ctx.resolve_field_ref(node.name, layout, region_reg)
            return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(ctx.parse_literal(node.name))
    if isinstance(node, BinOpNode):
        left_reg = lower_expr_node(ctx, node.left, layout, region_reg)
        right_reg = lower_expr_node(ctx, node.right, layout, region_reg)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=[node.op, left_reg, right_reg],
        )
        return result_reg
    logger.warning("Unknown expression node type: %s", type(node).__name__)
    return ctx.const_to_reg(0)
