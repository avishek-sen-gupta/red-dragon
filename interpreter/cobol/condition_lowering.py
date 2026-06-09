"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from functools import reduce

from interpreter.cobol.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    FunctionNode,
    LiteralNode,
    RefModNode,
)
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.condition_name import ConditionValue
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.func_name import FuncName
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import Binop, Const, CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_88_value_reg(
    ctx: EmitContext, raw: str, parent_is_alpha: bool, parent_byte_length: int = 1
) -> Register:
    """Build the comparison-value register for one side of an 88 VALUE.

    On a numeric parent the value is parsed (digit string -> int/float) so it
    compares against the decoded numeric value. On an ALPHANUMERIC (PIC X) parent
    the field decodes to its CHARACTER string, so the 88 VALUE must compare as a
    character literal too — a digit-character VALUE like '1' must stay the string
    "1" (not be coerced to int 1, which never equals the decoded "1"). This is
    the read-side counterpart of the SET <88> TO TRUE character write
    (red-dragon-0sq2).

    A figurative-constant VALUE (LOW-VALUES / SPACES / ZEROS / HIGH-VALUES) on an
    alphanumeric parent must expand to its fill character repeated to the parent
    field's byte length — NOT compared as the literal text 'LOW-VALUES'. This is
    the read-side counterpart of SET <88-figurative> TO TRUE (CardDemo COACTUPC
    ACUP-DETAILS-NOT-FETCHED VALUES LOW-VALUES, SPACES).
    """
    fill = _FIGURATIVE_FILL.get(raw.upper())
    if fill is not None:
        # Numeric parent + ZEROS -> integer 0; otherwise build the fill string
        # sized to the parent field so equality holds against the decoded field.
        if not parent_is_alpha and raw.upper() in ("ZERO", "ZEROS", "ZEROES"):
            return ctx.const_to_reg(0)
        return ctx.const_to_reg('"' + fill * max(parent_byte_length, 1) + '"')
    if parent_is_alpha:
        return ctx.const_to_reg(f'"{raw}"')
    return ctx.const_to_reg(ctx.parse_literal(raw))


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
    parent_is_alpha = (
        parent_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC
    )
    parent_reg = ctx.emit_decode_field(parent_rr, parent_ref.fl, parent_ref.offset_reg)

    parent_len = parent_ref.fl.byte_length

    if cv.is_range:
        from_reg = _emit_88_value_reg(ctx, cv.from_val, parent_is_alpha, parent_len)
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
        to_reg = _emit_88_value_reg(ctx, cv.to_val, parent_is_alpha, parent_len)
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

    value_reg = _emit_88_value_reg(ctx, cv.from_val, parent_is_alpha, parent_len)
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
    elif "class" in node:
        # Class condition: {"class": "NUMERIC"|"ALPHABETIC"|..., "operand": <expr>}
        inner = _lower_class_condition(ctx, node, materialised)
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
    """Return the byte length of a {"kind":"ref"} field operand, else None.

    For a reference-modified operand WS-S(start:len) with a literal length, the
    sliced length governs (so a figurative sibling is sized to the slice, not the
    whole field). A non-literal ref-mod length falls back to the full field.
    """
    if expr.get("kind") == "ref":
        if "ref_mod_start" in expr:
            slice_len = _ref_mod_slice_length(expr)
            if slice_len is not None:
                return slice_len
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


# Figuratives whose natural class is alphanumeric (character) rather than
# numeric. ZERO/ZEROS is numeric and is intentionally excluded so a
# numeric-DISPLAY field still compares to it by value.
_ALPHANUMERIC_FIGURATIVES: frozenset[str] = frozenset(
    {
        "SPACE",
        "SPACES",
        "LOW-VALUE",
        "LOW-VALUES",
        "HIGH-VALUE",
        "HIGH-VALUES",
        "QUOTE",
        "QUOTES",
    }
)


def _is_alphanumeric_operand(expr: dict) -> bool:
    """True if an operand is alphanumeric (character) data by its kind alone.

    Covers an alphanumeric figurative (SPACES / LOW-VALUES / HIGH-VALUES /
    QUOTES — not numeric ZEROS) and a quoted non-numeric character literal
    (e.g. '*'). A numeric literal (e.g. 11) is NOT alphanumeric. Determined
    structurally from the operand dict — no source-text sniffing.
    """
    kind = expr.get("kind")
    if kind == "figurative":
        return str(expr.get("value", "")).upper() in _ALPHANUMERIC_FIGURATIVES
    if kind == "lit":
        value = str(expr.get("value", ""))
        return value[:1] in ("'", '"')
    return False


def _is_zoned_display_field(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
) -> bool:
    """True if an operand is a reference to a USAGE DISPLAY numeric (zoned) field.

    COMP-3 / binary numerics are a different category and are deliberately
    excluded — only ZONED_DECIMAL carries a meaningful zoned character form.
    A reference-modified operand is already character-sliced, so it is excluded.
    """
    if expr.get("kind") != "ref" or "ref_mod_start" in expr:
        return False
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return False
    ref, _ = ctx.resolve_field_ref(name, materialised)
    return ref.fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL


def _lower_relation_operand(
    ctx: EmitContext,
    expr: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower one side of a relation, resolving figuratives against the sibling.

    Special case (red-dragon-dmu8): when this operand is a numeric USAGE DISPLAY
    (zoned) field and the *sibling* is alphanumeric (a non-numeric figurative or
    a quoted character literal), COBOL compares the numeric operand by its zoned
    CHARACTER (display) representation, not its decoded integer value. Decode it
    to its display digit string so both sides compare as character data. This is
    scoped to unsigned-effective values: the raw zoned bytes are used, so a
    trailing-sign overpunch (if any) would be carried verbatim — acceptable for
    the SPACES / LOW-VALUES / placeholder cases this targets.
    """
    if expr.get("kind") == "figurative":
        return _lower_figurative(ctx, expr, sibling, materialised)
    if _is_zoned_display_field(ctx, expr, materialised) and _is_alphanumeric_operand(
        sibling
    ):
        name = expr.get("name", "")
        ref, rr = ctx.resolve_field_ref(name, materialised)
        return ctx.emit_decode_zoned_display(rr, ref.fl, ref.offset_reg)
    if (
        _is_alphanumeric_operand(expr)
        and expr.get("kind") == "lit"
        and _is_zoned_display_field(ctx, sibling, materialised)
    ):
        # A non-numeric char literal compared to a numeric-DISPLAY field: COBOL
        # space-pads the (shorter) literal to the field width and compares
        # characters. Size to the sibling field so it lines up with the field's
        # zoned display string (red-dragon-dmu8).
        return _lower_padded_char_literal(ctx, expr, sibling, materialised)
    return _lower_expr_dict(ctx, expr, materialised)


def _lower_padded_char_literal(
    ctx: EmitContext,
    lit: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower a quoted char literal space-padded to the sibling field's width.

    The literal text carries its surrounding quotes (e.g. "'*'"); they are
    stripped, the content is right-padded with spaces to the sibling field's
    byte length, and emitted as a string constant.
    """
    raw = str(lit.get("value", ""))
    if len(raw) >= 2 and raw[0] in ("'", '"') and raw[-1] == raw[0]:
        content = raw[1:-1]
    else:
        content = raw
    width = _field_byte_length(ctx, sibling, materialised)
    if width is None or width < len(content):
        width = len(content)
    padded = content.ljust(width)
    return ctx.const_to_reg(f'"{padded}"')


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


_CLASS_BUILTIN: dict[str, str] = {
    "NUMERIC": BuiltinName.IS_NUMERIC,
    "ALPHABETIC": BuiltinName.IS_ALPHABETIC,
    "ALPHABETIC-LOWER": BuiltinName.IS_ALPHABETIC_LOWER,
    "ALPHABETIC-UPPER": BuiltinName.IS_ALPHABETIC_UPPER,
}


def _lower_class_condition(
    ctx: EmitContext,
    node: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower a class condition {"class": <NAME>, "operand": <expr>} to a boolean.

    The operand's decoded value is converted to character data and passed to the
    matching COBOL-layer class-test builtin (__is_numeric / __is_alphabetic / ...).
    An unknown class never matches (rather than silently evaluating TRUE).
    """
    class_name = str(node.get("class", "")).upper()
    builtin = _CLASS_BUILTIN.get(class_name)
    if builtin is None:
        logger.warning("unknown class condition %r — never matching", class_name)
        result = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=result, value="False"))
        return result

    value_reg = _lower_expr_dict(ctx, node.get("operand", {}), materialised)
    value_str_reg = ctx.emit_to_string(value_reg)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result,
            func_name=FuncName(builtin),
            args=(Register(str(value_str_reg)),),
        )
    )
    return result


def _ref_mod_slice_length(expr: dict) -> int | None:
    """Return the static slice length of a ref-mod operand, if it is a literal."""
    rm_len = expr.get("ref_mod_length")
    if isinstance(rm_len, dict) and rm_len.get("kind") == "lit":
        try:
            return int(rm_len.get("value", ""))
        except (TypeError, ValueError):
            return None
    return None


def _lower_ref_mod_operand(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower a reference-modified field operand WS-S(start:length) in a condition.

    Decodes the underlying field to its character string and slices it with the
    1-based start (converted to 0-based) and optional length. The start and
    length are themselves expression dicts (re-evaluated each call, so a loop
    variable subscript reflects the current iteration). Returns a string-valued
    register so it compares correctly against figurative/string siblings.
    """
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return ctx.const_to_reg(ctx.parse_literal(name))

    ref, rr = ctx.resolve_field_ref(name, materialised)
    full_str_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)

    start_1based_reg = _lower_expr_dict(ctx, expr["ref_mod_start"], materialised)
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

    rm_len = expr.get("ref_mod_length")
    if isinstance(rm_len, dict):
        length_reg = _lower_expr_dict(ctx, rm_len, materialised)
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
    return sliced_reg


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
        if "ref_mod_start" in expr:
            return _lower_ref_mod_operand(ctx, expr, materialised)
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

    if kind == "function":
        # Intrinsic FUNCTION call as a relation operand (red-dragon-ge72), e.g.
        # FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B). Delegate to the shared
        # function-operand lowering so the call + args produce a computed value
        # register that compares normally.
        from interpreter.cobol.ref_mod import FunctionCallOperand
        from interpreter.cobol.lower_arithmetic import lower_function_operand

        operand = FunctionCallOperand.from_dict(expr)
        return lower_function_operand(ctx, operand, materialised)

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
            ref, rr = ctx.resolve_field_ref(
                node.name, materialised, subscripts=node.subscripts
            )
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
        ref, rr = ctx.resolve_field_ref(
            node.name, materialised, subscripts=node.subscripts
        )
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
    if isinstance(node, FunctionNode):
        # Intrinsic FUNCTION call as an expression/relation operand (e.g.
        # FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B), or COMPUTE X =
        # FUNCTION TRIM(WS-A)). Each arg is lowered to a string-valued register
        # then passed to the COBOL-layer builtin (red-dragon-ge72).
        from interpreter.cobol.lower_arithmetic import (
            _INTRINSIC_FUNCTIONS,
            _lower_function_arg_to_string,
        )

        builtin = _INTRINSIC_FUNCTIONS.get(node.name.upper())
        arg_regs = tuple(
            _lower_function_arg_to_string(
                ctx, _expr_node_to_arg_dict(arg), materialised
            )
            for arg in node.args
        )
        if builtin is None:
            logger.warning(
                "Unsupported COBOL intrinsic FUNCTION %r — falling back to first argument",
                node.name,
            )
            return arg_regs[0] if arg_regs else ctx.const_to_reg('""')
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName(builtin),
                args=arg_regs,
            )
        )
        return result_reg
    logger.warning("Unknown expression node type: %s", type(node).__name__)
    return ctx.const_to_reg(0)


def _expr_node_to_arg_dict(node: ExprNode) -> dict:
    """Convert an ExprNode argument back into the operand-dict shape consumed by
    ``_lower_function_arg_to_string`` (ref/lit/binop/neg).

    Intrinsic-function arguments are simple operands (a field ref or literal in
    CardDemo's usage); richer arithmetic args round-trip through the generic
    expression kinds.
    """
    if isinstance(node, LiteralNode):
        return {"kind": "lit", "value": node.value}
    if isinstance(node, FieldRefNode):
        return {"kind": "ref", "name": node.name}
    if isinstance(node, BinOpNode):
        return {
            "kind": "binop",
            "op": node.op,
            "left": _expr_node_to_arg_dict(node.left),
            "right": _expr_node_to_arg_dict(node.right),
        }
    if isinstance(node, FunctionNode):
        return {
            "kind": "function",
            "name": node.name,
            "args": [_expr_node_to_arg_dict(a) for a in node.args],
        }
    # RefModNode and any other shape: stringify via the ref name as a fallback.
    return {"kind": "ref", "name": getattr(node, "name", "")}
