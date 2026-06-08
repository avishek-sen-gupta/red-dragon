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
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.func_name import FuncName
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import Binop, Const, CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_single_value_test(
    ctx: EmitContext,
    cv: ConditionValue,
    materialised: MaterialisedSectionedLayout,
    parent_field_name: str,
) -> Register:
    """Emit IR to test a parent field against a single ConditionValue.

    For discrete values: parent_field == value
    For THRU ranges: parent_field >= from AND parent_field <= to
    """
    parent_ref, parent_rr = ctx.resolve_field_ref(parent_field_name, materialised)
    parent_reg = ctx.emit_decode_field(parent_rr, parent_ref.fl, parent_ref.offset_reg)

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

        parent_ref2, parent_rr2 = ctx.resolve_field_ref(parent_field_name, materialised)
        parent_reg2 = ctx.emit_decode_field(
            parent_rr2, parent_ref2.fl, parent_ref2.offset_reg
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
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Expand a level-88 condition name into field comparison IR.

    For single-value conditions: parent == value
    For multi-value: parent == v1 OR parent == v2 OR ...
    For THRU ranges: parent >= from AND parent <= to
    Mixed: combines all with OR.
    """
    entry = condition_index.lookup(condition_name)
    value_regs = [
        _emit_single_value_test(ctx, cv, materialised, entry.parent_field_name)
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
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex = ConditionNameIndex({}),
) -> Register:
    """Lower a structured condition dict to a register holding a boolean."""
    return _lower_condition_node(ctx, condition, materialised, condition_index)


def _lower_condition_node(
    ctx: EmitContext,
    node: dict,
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex,
) -> Register:
    """Recursively walk a structured condition dict node and emit IR."""
    if "op" in node:
        # Compound: {"op": "AND"/"OR", "left": {...}, "right": {...}}
        op = node["op"]
        left_reg = _lower_condition_node(
            ctx, node["left"], materialised, condition_index
        )
        right_reg = _lower_condition_node(
            ctx, node["right"], materialised, condition_index
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
            inner = _expand_condition_name(ctx, name, condition_index, materialised)
        else:
            # Fall back to string lowering for unresolved names
            inner = _lower_condition_str(ctx, name, materialised, condition_index)
    elif "condition" in node:
        # Nested parenthesised condition
        inner = _lower_condition_node(
            ctx, node["condition"], materialised, condition_index
        )
    elif "relation" in node:
        # Structured relation: {"left": <expr>, "op": "...", "right": <expr>}
        inner = _lower_relation_node(ctx, node["relation"], materialised)
    else:
        # Fallback: flat text (CLASS/SIGN conditions, EVALUATE/SEARCH callers)
        inner = _lower_condition_str(
            ctx, node.get("text", ""), materialised, condition_index
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


# Canonical figurative-constant fill characters. The value is built sized to the
# *sibling* operand's field length so equality holds against the decoded field.
_FIGURATIVE_FILL: dict[str, str] = {
    "SPACE": " ",
    "SPACES": " ",
    "ZERO": "0",
    "ZEROS": "0",
    "ZEROES": "0",
    "LOW-VALUE": "\x00",
    "LOW-VALUES": "\x00",
    "HIGH-VALUE": "\xff",
    "HIGH-VALUES": "\xff",
    "QUOTE": '"',
    "QUOTES": '"',
}

_DEFAULT_FIGURATIVE_LEN = 1


def _field_byte_length(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
) -> int | None:
    """Return the byte length of a {"kind":"ref"} field operand, else None."""
    if expr.get("kind") == "ref":
        name = expr.get("name", "")
        if ctx.has_field(name, materialised):
            ref, _ = ctx.resolve_field_ref(name, materialised)
            return ref.fl.byte_length
    return None


def _lower_figurative(
    ctx: EmitContext,
    fig: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower a {"kind":"figurative","value":...} operand.

    The figurative is materialised as a string literal whose length matches the
    *sibling* operand's field (so it equals the decoded field when the field
    actually holds that figurative). Falls back to a single character when the
    sibling is not a field.
    """
    value = str(fig.get("value", "")).upper()
    fill = _FIGURATIVE_FILL.get(value, " ")
    length = _field_byte_length(ctx, sibling, materialised)
    if length is None:
        length = _DEFAULT_FIGURATIVE_LEN
    literal = fill * length
    return ctx.const_to_reg(f'"{literal}"')


def _lower_relation_operand(
    ctx: EmitContext,
    expr: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower one side of a relation, resolving figuratives against the sibling."""
    if expr.get("kind") == "figurative":
        return _lower_figurative(ctx, expr, sibling, materialised)
    return _lower_expr_dict(ctx, expr, materialised)


def _lower_relation_node(
    ctx: EmitContext,
    rel: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower a structured relation dict {"left": <expr>, "op": "...", "right": <expr>}."""
    left_reg = _lower_relation_operand(ctx, rel["left"], rel["right"], materialised)
    right_reg = _lower_relation_operand(ctx, rel["right"], rel["left"], materialised)
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
    materialised: MaterialisedSectionedLayout,
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
        if ctx.has_field(name, materialised):
            ref, rr = ctx.resolve_field_ref(name, materialised)
            return ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(ctx.parse_literal(name))

    if kind == "lit":
        return ctx.const_to_reg(ctx.parse_literal(expr.get("value", "")))

    if kind == "binop":
        left_reg = _lower_expr_dict(ctx, expr["left"], materialised)
        right_reg = _lower_expr_dict(ctx, expr["right"], materialised)
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
        inner = _lower_expr_dict(ctx, expr["expr"], materialised)
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
    materialised: MaterialisedSectionedLayout,
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
        return _expand_condition_name(ctx, parts[0], condition_index, materialised)

    if len(parts) >= 3:
        left_name = parts[0]
        if parts[1] == "NOT" and len(parts) >= 4:
            op = "!="
            right_val = parts[3]
        else:
            op_map = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "=": "=="}
            op = op_map.get(parts[1], "==")
            right_val = parts[2]

        if ctx.has_field(left_name, materialised):
            left_ref, left_rr = ctx.resolve_field_ref(left_name, materialised)
            left_reg = ctx.emit_decode_field(left_rr, left_ref.fl, left_ref.offset_reg)
        else:
            left_reg = ctx.const_to_reg(ctx.parse_literal(left_name))

        right_parsed = ctx.parse_literal(right_val)
        if isinstance(right_parsed, str) and ctx.has_field(right_parsed, materialised):
            right_ref, right_rr = ctx.resolve_field_ref(right_parsed, materialised)
            right_reg = ctx.emit_decode_field(
                right_rr, right_ref.fl, right_ref.offset_reg
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

    # CLASS/SIGN conditions and other shapes are not yet structured here. An
    # unparseable condition must NOT silently evaluate TRUE — doing so would make
    # whole WHEN/IF branches fire unconditionally. Warn and never-match instead.
    # (Full CLASS/SIGN structuring is deferred — see red-dragon-z31u.)
    logger.warning("unparseable condition %r — never matching", condition)
    result = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result, value="False"))
    return result


def lower_expr_node(
    ctx: EmitContext,
    node: ExprNode,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Walk an expression tree node and emit IR. Returns result register."""
    if isinstance(node, LiteralNode):
        return ctx.const_to_reg(ctx.parse_literal(node.value))
    if isinstance(node, FieldRefNode):
        if ctx.has_field(node.name, materialised):
            ref, rr = ctx.resolve_field_ref(node.name, materialised)
            return ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(ctx.parse_literal(node.name))
    if isinstance(node, BinOpNode):
        left_reg = lower_expr_node(ctx, node.left, materialised)
        right_reg = lower_expr_node(ctx, node.right, materialised)
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
        ref, rr = ctx.resolve_field_ref(node.name, materialised)
        full_str_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        start_1based_reg = lower_expr_node(ctx, node.ref_mod_start, materialised)
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
            length_reg = lower_expr_node(ctx, node.ref_mod_length, materialised)
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
