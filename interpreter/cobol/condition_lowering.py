# pyright: standard
"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from functools import reduce

from interpreter.cobol.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    LiteralNode,
)
from interpreter.cobol.condition_name import ConditionValue
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import Binop, Const
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_single_value_test(
    ctx: EmitContext,
    cv: ConditionValue,
    layout: DataLayout,
    region_reg: str,
    parent_field_name: str,
) -> str:
    """Emit IR to test a parent field against a single ConditionValue.

    For discrete values: parent_field == value
    For THRU ranges: parent_field >= from AND parent_field <= to
    """
    parent_ref = ctx.resolve_field_ref(parent_field_name, layout, region_reg)
    parent_reg = ctx.emit_decode_field(region_reg, parent_ref.fl, parent_ref.offset_reg)

    if cv.is_range:
        from_reg = ctx.const_to_reg(ctx.parse_literal(cv.from_val))
        ge_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=ge_result,
                operator=resolve_binop(">="),
                left=Register(str(parent_reg)),
                right=Register(str(from_reg)),
            )
        )

        parent_ref2 = ctx.resolve_field_ref(parent_field_name, layout, region_reg)
        parent_reg2 = ctx.emit_decode_field(
            region_reg, parent_ref2.fl, parent_ref2.offset_reg
        )
        to_reg = ctx.const_to_reg(ctx.parse_literal(cv.to_val))
        le_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=le_result,
                operator=resolve_binop("<="),
                left=Register(str(parent_reg2)),
                right=Register(str(to_reg)),
            )
        )

        and_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=and_result,
                operator=resolve_binop("and"),
                left=ge_result,
                right=le_result,
            )
        )
        return and_result  # type: ignore[return-value]  # see red-dragon-pn3f

    value_reg = ctx.const_to_reg(ctx.parse_literal(cv.from_val))
    eq_result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=eq_result,
            operator=resolve_binop("=="),
            left=Register(str(parent_reg)),
            right=Register(str(value_reg)),
        )
    )
    return eq_result  # type: ignore[return-value]  # see red-dragon-pn3f


def _emit_or_chain(ctx: EmitContext, regs: list[str]) -> str:
    """Combine a list of boolean registers with OR. Returns result register."""
    return reduce(
        lambda acc, reg: _emit_or(ctx, acc, reg),
        regs[1:],
        regs[0],
    )


def _emit_or(ctx: EmitContext, left_reg: str, right_reg: str) -> str:
    """Emit a single OR between two boolean registers."""
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop("or"),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        )
    )
    return result  # type: ignore[return-value]  # see red-dragon-pn3f


def _expand_condition_name(
    ctx: EmitContext,
    condition_name: str,
    condition_index: ConditionNameIndex,
    layout: DataLayout,
    region_reg: str,
) -> str:
    """Expand a level-88 condition name into field comparison IR.

    For single-value conditions: parent == value
    For multi-value: parent == v1 OR parent == v2 OR ...
    For THRU ranges: parent >= from AND parent <= to
    Mixed: combines all with OR.
    """
    entry = condition_index.lookup(condition_name)
    value_regs = [
        _emit_single_value_test(ctx, cv, layout, region_reg, entry.parent_field_name)
        for cv in entry.values
    ]

    if not value_regs:
        result = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=result, value=True))  # type: ignore[arg-type]  # see red-dragon-0qgg
        return result  # type: ignore[return-value]  # see red-dragon-pn3f

    return _emit_or_chain(ctx, value_regs)


def lower_condition(
    ctx: EmitContext,
    condition: str,
    layout: DataLayout,
    region_reg: str,
    condition_index: ConditionNameIndex = ConditionNameIndex({}),
) -> str:
    """Lower a simple condition string to a register holding a boolean.

    Supports:
    - "field OP value" where OP is >, <, >=, <=, =, NOT =
    - Single-token condition names (level-88) that expand to parent comparisons
    """
    parts = condition.split()

    if len(parts) == 1 and condition_index.has_condition(parts[0]):
        logger.debug("Expanding condition name: %s", parts[0])
        return _expand_condition_name(
            ctx, parts[0], condition_index, layout, region_reg
        )

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
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop(op),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            )
        )
        return result  # type: ignore[return-value]  # see red-dragon-pn3f

    result = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result, value=True))  # type: ignore[arg-type]  # see red-dragon-0qgg
    return result  # type: ignore[return-value]  # see red-dragon-pn3f


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
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(node.op),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            )
        )
        return result_reg  # type: ignore[return-value]  # see red-dragon-pn3f
    logger.warning("Unknown expression node type: %s", type(node).__name__)
    return ctx.const_to_reg(0)
