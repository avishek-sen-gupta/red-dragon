"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from functools import reduce

from interpreter.cobol.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    LiteralNode,
    RefModNode,
)
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_name import ConditionValue
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.func_name import FuncName
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import Binop, Const, CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_single_value_test(
    ctx: EmitContext,
    cv: ConditionValue,
    layout: DataLayout,
    region_reg: Register,
    parent_field_name: str,
) -> Register:
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
        return and_result

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
    return eq_result


def _emit_or_chain(ctx: EmitContext, regs: list[Register]) -> Register:
    """Combine a list of boolean registers with OR. Returns result register."""
    return reduce(
        lambda acc, reg: _emit_or(ctx, acc, reg),
        regs[1:],
        regs[0],
    )


def _emit_or(ctx: EmitContext, left_reg: Register, right_reg: Register) -> Register:
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
    return result


def _expand_condition_name(
    ctx: EmitContext,
    condition_name: str,
    condition_index: ConditionNameIndex,
    layout: DataLayout,
    region_reg: Register,
) -> Register:
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
        ctx.emit_inst(Const(result_reg=result, value="True"))
        return result

    return _emit_or_chain(ctx, value_regs)


def lower_condition(
    ctx: EmitContext,
    condition: dict,
    layout: DataLayout,
    region_reg: Register,
    condition_index: ConditionNameIndex = ConditionNameIndex({}),
) -> Register:
    """Lower a structured condition dict to a register holding a boolean."""
    return _lower_condition_node(ctx, condition, layout, region_reg, condition_index)


def _lower_condition_node(
    ctx: EmitContext,
    node: dict,
    layout: DataLayout,
    region_reg: Register,
    condition_index: ConditionNameIndex,
) -> Register:
    """Recursively walk a structured condition dict node and emit IR."""
    if "op" in node:
        # Compound: {"op": "AND"/"OR", "left": {...}, "right": {...}}
        op = node["op"]
        left_reg = _lower_condition_node(
            ctx, node["left"], layout, region_reg, condition_index
        )
        right_reg = _lower_condition_node(
            ctx, node["right"], layout, region_reg, condition_index
        )
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop("and" if op == "AND" else "or"),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            )
        )
        return result

    not_flag: bool = node.get("not", False)

    if "condition_name" in node:
        # 88-level condition name reference
        name = node["condition_name"]
        if condition_index.has_condition(name):
            inner = _expand_condition_name(
                ctx, name, condition_index, layout, region_reg
            )
        else:
            # Fall back to string lowering for unresolved names
            inner = _lower_condition_str(ctx, name, layout, region_reg, condition_index)
    elif "condition" in node:
        # Nested parenthesised condition
        inner = _lower_condition_node(
            ctx, node["condition"], layout, region_reg, condition_index
        )
    elif "relation" in node:
        # Structured relation: {"left": <expr>, "op": "...", "right": <expr>}
        inner = _lower_relation_node(ctx, node["relation"], layout, region_reg)
    else:
        # Fallback: flat text (CLASS/SIGN conditions, EVALUATE/SEARCH callers)
        inner = _lower_condition_str(
            ctx, node.get("text", ""), layout, region_reg, condition_index
        )

    if not not_flag:
        return inner

    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop("=="),
            left=Register(str(inner)),
            right=Register(str(ctx.const_to_reg(False))),
        )
    )
    return result


_OP_MAP: dict[str, str] = {
    "==": "==",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "!=": "!=",
}


def _lower_relation_node(
    ctx: EmitContext,
    rel: dict,
    layout: DataLayout,
    region_reg: Register,
) -> Register:
    """Lower a structured relation dict {"left": <expr>, "op": "...", "right": <expr>}."""
    left_reg = _lower_expr_dict(ctx, rel["left"], layout, region_reg)
    right_reg = _lower_expr_dict(ctx, rel["right"], layout, region_reg)
    op = _OP_MAP.get(rel.get("op", "=="), "==")
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(op),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        )
    )
    return result


def _lower_expr_dict(
    ctx: EmitContext,
    expr: dict,
    layout: DataLayout,
    region_reg: Register,
) -> Register:
    """Recursively lower an expression dict node to a register.

    Supported kinds:
    - {"kind": "ref", "name": "WS-A"} — field reference or literal fallback
    - {"kind": "lit", "value": "10"} — literal constant
    - {"kind": "binop", "op": "+", "left": <expr>, "right": <expr>} — arithmetic
    - {"kind": "neg", "expr": <expr>} — unary negation
    """
    kind = expr.get("kind", "lit")

    if kind == "ref":
        name = expr.get("name", "")
        if ctx.has_field(name, layout):
            ref = ctx.resolve_field_ref(name, layout, region_reg)
            return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(ctx.parse_literal(name))

    if kind == "lit":
        return ctx.const_to_reg(ctx.parse_literal(expr.get("value", "")))

    if kind == "binop":
        left_reg = _lower_expr_dict(ctx, expr["left"], layout, region_reg)
        right_reg = _lower_expr_dict(ctx, expr["right"], layout, region_reg)
        op = _OP_MAP.get(expr.get("op", "+"), "+")
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop(op),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            )
        )
        return result

    if kind == "neg":
        inner = _lower_expr_dict(ctx, expr["expr"], layout, region_reg)
        zero_reg = ctx.const_to_reg(0)
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop("-"),
                left=Register(str(zero_reg)),
                right=Register(str(inner)),
            )
        )
        return result

    # Unknown kind — treat as empty literal
    return ctx.const_to_reg(ctx.parse_literal(""))


def _lower_condition_str(
    ctx: EmitContext,
    condition: str,
    layout: DataLayout,
    region_reg: Register,
    condition_index: ConditionNameIndex,
) -> Register:
    """Lower a flat condition string to a boolean register.

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
        return result

    result = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result, value="True"))
    return result


def lower_expr_node(
    ctx: EmitContext,
    node: ExprNode,
    layout: DataLayout,
    region_reg: Register,
) -> Register:
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
        return result_reg
    if isinstance(node, RefModNode):
        ref = ctx.resolve_field_ref(node.name, layout, region_reg)
        full_str_reg = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        start_1based_reg = lower_expr_node(ctx, node.ref_mod_start, layout, region_reg)
        one_reg = ctx.const_to_reg(1)
        start_0based_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0based_reg,
                operator=resolve_binop("-"),
                left=Register(str(start_1based_reg)),
                right=Register(str(one_reg)),
            )
        )
        if node.ref_mod_length is not None:
            length_reg = lower_expr_node(ctx, node.ref_mod_length, layout, region_reg)
        else:
            length_reg = ctx.const_to_reg(999999)
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(
                    Register(str(full_str_reg)),
                    Register(str(start_0based_reg)),
                    Register(str(length_reg)),
                ),
            )
        )
        # Convert string slice result back to float for arithmetic operations
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName("float"),
                args=(Register(str(sliced_reg)),),
            )
        )
        return result_reg
    logger.warning("Unknown expression node type: %s", type(node).__name__)
    return ctx.const_to_reg(0)
