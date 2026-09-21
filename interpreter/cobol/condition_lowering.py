"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from functools import reduce

from interpreter.cobol.arithmetic_scale import (
    expression_is_floating,
    node_scale,
    operand_dmax,
)
from interpreter.cobol.cobol_constants import BuiltinName
from cobol_asg.cobol_expression import (
    BinOpNode,
    DfhRespNode,
    ExprNode,
    FieldRefNode,
    FigurativeNode,
    FunctionNode,
    LengthOfNode,
    LiteralNode,
    RefModNode,
    expr_from_dict,
    expr_to_dict,
)
from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.condition_name import ConditionValue
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction, Const
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_88_value_reg(
    ctx: EmitContext,
    raw: str,
    parent_is_alpha: bool,
    parent_byte_length: int = 1,
    *,
    span: SourceSpan | None = None,
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
            return ctx.const_to_reg(0, span=span)
        return ctx.const_to_reg(fill * max(parent_byte_length, 1), span=span)
    if parent_is_alpha:
        # The parent decodes to its full byte width (no trailing-space trim), so
        # a VALUE shorter than the parent must be right-space-padded to that width
        # for the equality to hold — mirroring how SET <88> TO TRUE writes the
        # padded value. (CardDemo COCRDSLC: 88 FOUND-CARDS-FOR-ACCOUNT VALUE
        # '   Displaying...' on a PIC X(40) flag.)
        return ctx.const_to_reg(raw.ljust(max(parent_byte_length, len(raw))), span=span)
    return ctx.const_to_reg(ctx.parse_literal(raw), span=span)


def _emit_single_value_test(
    ctx: EmitContext,
    cv: ConditionValue,
    materialised: MaterialisedSectionedLayout,
    parent_field_name: str,
    subscripts: tuple = (),
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Emit IR to test a parent field against a single ConditionValue.

    For discrete values: parent_field == value
    For THRU ranges: parent_field >= from AND parent_field <= to

    ``subscripts`` selects the OCCURS element when the level-88 is defined on a
    table item and referenced with a subscript (e.g. ``SEL-OK(I)``).
    """
    parent_ref, parent_rr = ctx.resolve_field_ref(
        parent_field_name, materialised, subscripts=subscripts, span=span
    )
    parent_is_alpha = parent_ref.fl.type_descriptor.holds_characters
    parent_reg = ctx.emit_decode_field(
        parent_rr,
        parent_ref.fl,
        parent_ref.offset_reg,
        extent=parent_ref.extent,
        span=span,
    )

    parent_len = parent_ref.fl.byte_length

    if cv.is_range:
        from_reg = _emit_88_value_reg(
            ctx, cv.from_val, parent_is_alpha, parent_len, span=span
        )
        ge_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=ge_result,
                operator=resolve_binop(">="),
                left=Register(str(parent_reg)),
                right=Register(str(from_reg)),
            ),
            span=span,
        )

        parent_ref2, parent_rr2 = ctx.resolve_field_ref(
            parent_field_name, materialised, subscripts=subscripts, span=span
        )
        parent_reg2 = ctx.emit_decode_field(
            parent_rr2,
            parent_ref2.fl,
            parent_ref2.offset_reg,
            extent=parent_ref2.extent,
            span=span,
        )
        to_reg = _emit_88_value_reg(
            ctx, cv.to_val, parent_is_alpha, parent_len, span=span
        )
        le_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=le_result,
                operator=resolve_binop("<="),
                left=Register(str(parent_reg2)),
                right=Register(str(to_reg)),
            ),
            span=span,
        )

        and_result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=and_result,
                operator=resolve_binop("and"),
                left=ge_result,
                right=le_result,
            ),
            span=span,
        )
        return and_result

    value_reg = _emit_88_value_reg(
        ctx, cv.from_val, parent_is_alpha, parent_len, span=span
    )
    eq_result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=eq_result,
            operator=resolve_binop("=="),
            left=Register(str(parent_reg)),
            right=Register(str(value_reg)),
        ),
        span=span,
    )
    return eq_result


def _emit_or_chain(
    ctx: EmitContext, regs: list[Register], *, span: SourceSpan | None = None
) -> Register:
    """Combine a list of boolean registers with OR. Returns result register."""
    return reduce(
        lambda acc, reg: _emit_or(ctx, acc, reg, span=span),
        regs[1:],
        regs[0],
    )


def _emit_or(
    ctx: EmitContext,
    left_reg: Register,
    right_reg: Register,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Emit a single OR between two boolean registers."""
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop("or"),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        ),
        span=span,
    )
    return result


def _expand_condition_name(
    ctx: EmitContext,
    condition_name: str,
    condition_index: ConditionNameIndex,
    materialised: MaterialisedSectionedLayout,
    subscripts: tuple = (),
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Expand a level-88 condition name into field comparison IR.

    For single-value conditions: parent == value
    For multi-value: parent == v1 OR parent == v2 OR ...
    For THRU ranges: parent >= from AND parent <= to
    Mixed: combines all with OR.

    ``subscripts`` selects the OCCURS element for a table-defined 88
    (e.g. ``SEL-OK(I)``).
    """
    entry = condition_index.lookup(condition_name)
    value_regs = [
        _emit_single_value_test(
            ctx,
            cv,
            materialised,
            entry.parent_field_name,
            subscripts=subscripts,
            span=span,
        )
        for cv in entry.values
    ]

    if not value_regs:
        result = ctx.fresh_reg()
        ctx.emit_inst(Const.bool_(result, True), span=span)
        return result

    return _emit_or_chain(ctx, value_regs, span=span)


def lower_condition(
    ctx: EmitContext,
    condition: dict,
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex = ConditionNameIndex({}),
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a structured condition dict to a register holding a boolean."""
    return _lower_condition_node(
        ctx, condition, materialised, condition_index, span=span
    )


def _extract_implied_relation(node: dict) -> tuple[bool, str, dict] | None:
    """Return (not_flag, op, left_expr_dict) from the rightmost full relation
    in a condition subtree, or None if no relation is found.

    Used to repair abbreviated-operand nodes that ProLeap mis-serialises as
    {"condition_name": X} when X is a plain data field (not level-88): COBOL
    abbreviated conditions inherit the comparison subject and operator from the
    most recently stated full relation on the left of the compound.
    """
    if "relation" in node:
        rel = node["relation"]
        return (node.get("not", False), rel.get("op", "=="), rel.get("left", {}))
    if "op" in node:
        result = _extract_implied_relation(node["right"])
        if result is not None:
            return result
        return _extract_implied_relation(node["left"])
    return None


def _lower_condition_node(
    ctx: EmitContext,
    node: dict,
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Recursively walk a structured condition dict node and emit IR."""
    if "op" in node:
        # Compound: {"op": "AND"/"OR", "left": {...}, "right": {...}}
        op = node["op"]
        left_reg = _lower_condition_node(
            ctx, node["left"], materialised, condition_index, span=span
        )
        right_node = node["right"]
        # COBOL abbreviated conditions: ProLeap sometimes serialises a plain
        # data field as {"condition_name": X} (rather than an abbreviated
        # relation) when X is not a level-88.  Detect this and repair by
        # inheriting the comparison subject and operator from the nearest full
        # relation on the left side of the compound.
        if "condition_name" in right_node and not condition_index.has_condition(
            right_node["condition_name"]
        ):
            implied = _extract_implied_relation(node["left"])
            if implied is not None:
                implied_not, implied_op, implied_left = implied
                right_node = {
                    "not": implied_not,
                    "relation": {
                        "left": implied_left,
                        "op": implied_op,
                        "right": {
                            "kind": "ref",
                            "name": right_node["condition_name"],
                        },
                    },
                }
        right_reg = _lower_condition_node(
            ctx, right_node, materialised, condition_index, span=span
        )
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop("and" if op == "AND" else "or"),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            ),
            span=span,
        )
        return result

    not_flag: bool = node.get("not", False)

    if "condition_name" in node:
        # 88-level condition name reference
        name = node["condition_name"]
        subscripts = tuple(
            expr_from_dict(s) for s in node.get("condition_subscripts", [])
        )
        if condition_index.has_condition(name):
            inner = _expand_condition_name(
                ctx,
                name,
                condition_index,
                materialised,
                subscripts=subscripts,
                span=span,
            )
        else:
            # Fall back to string lowering for unresolved names
            inner = _lower_condition_str(
                ctx, name, materialised, condition_index, span=span
            )
    elif "condition" in node:
        # Nested parenthesised condition
        inner = _lower_condition_node(
            ctx, node["condition"], materialised, condition_index, span=span
        )
    elif "relation" in node:
        # Structured relation: {"left": <expr>, "op": "...", "right": <expr>}
        inner = _lower_relation_node(ctx, node["relation"], materialised, span=span)
    elif "class" in node:
        # Class condition: {"class": "NUMERIC"|"ALPHABETIC"|..., "operand": <expr>}
        inner = _lower_class_condition(ctx, node, materialised, span=span)
    elif "sign" in node:
        # Sign condition: {"sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}
        inner = _lower_sign_condition(ctx, node, materialised, span=span)
    else:
        # Fallback: flat text (CLASS/SIGN conditions, EVALUATE/SEARCH callers)
        inner = _lower_condition_str(
            ctx, node.get("text", ""), materialised, condition_index, span=span
        )

    if not not_flag:
        return inner

    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop("=="),
            left=Register(str(inner)),
            right=Register(str(ctx.const_to_reg(False, span=span))),
        ),
        span=span,
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
    *,
    span: SourceSpan | None = None,
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
            ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
            return ref.fl.byte_length
    return None


def _lower_figurative(
    ctx: EmitContext,
    fig: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a {"kind":"figurative","value":...} operand.

    The figurative is materialised as a string literal whose length matches the
    *sibling* operand's field (so it equals the decoded field when the field
    actually holds that figurative). Falls back to a single character when the
    sibling is not a field.
    """
    value = str(fig.get("value", "")).upper()
    # ZERO / ZEROS against a NUMERIC field compares by value (integer 0), not as
    # a zero-filled character string — otherwise "1000.00" <= "0000000000.00"
    # would be a (broken) number-vs-string comparison (red-dragon-z6ad family).
    if value in ("ZERO", "ZEROS", "ZEROES") and _is_numeric_field(
        ctx, sibling, materialised, span=span
    ):
        return ctx.const_to_reg(0, span=span)
    fill = _FIGURATIVE_FILL.get(value, " ")
    length = _field_byte_length(ctx, sibling, materialised, span=span)
    if length is None:
        length = _DEFAULT_FIGURATIVE_LEN
    literal = fill * length
    return ctx.const_to_reg(literal, span=span)


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
    *,
    span: SourceSpan | None = None,
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
    ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
    return ref.fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL


_NUMERIC_CATEGORIES: frozenset[CobolDataCategory] = frozenset(
    {
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.COMP3,
        CobolDataCategory.BINARY,
        CobolDataCategory.COMP1,
        CobolDataCategory.COMP2,
    }
)


def _is_numeric_field(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> bool:
    """True if an operand is a reference to a numeric field (zoned / COMP-3 /
    binary / float). A reference-modified operand is a character slice, excluded.
    """
    if expr.get("kind") != "ref" or "ref_mod_start" in expr:
        return False
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return False
    ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
    return ref.fl.type_descriptor.category in _NUMERIC_CATEGORIES


def _is_alphanumeric_field(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> bool:
    """True if an operand is a reference to an ALPHANUMERIC (PIC X) field, or a
    reference-modified slice (always character data)."""
    if expr.get("kind") != "ref":
        return False
    if "ref_mod_start" in expr:
        return True
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return False
    ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
    return ref.fl.type_descriptor.holds_characters


def _is_alphanumeric_sibling(
    ctx: EmitContext,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> bool:
    """An operand counts as alphanumeric for the zoned-display comparison rule
    when it is a non-numeric figurative / quoted char literal OR an alphanumeric
    field (or ref-mod slice)."""
    return _is_alphanumeric_operand(sibling) or _is_alphanumeric_field(
        ctx, sibling, materialised, span=span
    )


def _lower_relation_operand(
    ctx: EmitContext,
    expr: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
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
        return _lower_figurative(ctx, expr, sibling, materialised, span=span)
    if _is_zoned_display_field(
        ctx, expr, materialised, span=span
    ) and _is_alphanumeric_sibling(ctx, sibling, materialised, span=span):
        name = expr.get("name", "")
        subscripts = tuple(expr_from_dict(s) for s in expr.get("subscripts", []))
        ref, rr = ctx.resolve_field_ref(
            name,
            materialised,
            qualifiers=tuple(expr.get("qualifiers", ())),
            subscripts=subscripts,
            span=span,
        )
        return ctx.emit_decode_zoned_display(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
    if (
        _is_alphanumeric_operand(expr)
        and expr.get("kind") == "lit"
        and _is_zoned_display_field(ctx, sibling, materialised, span=span)
    ):
        # A non-numeric char literal compared to a numeric-DISPLAY field: COBOL
        # space-pads the (shorter) literal to the field width and compares
        # characters. Size to the sibling field so it lines up with the field's
        # zoned display string (red-dragon-dmu8).
        return _lower_padded_char_literal(ctx, expr, sibling, materialised, span=span)
    return _lower_expr_dict(ctx, expr, materialised, span=span)


def _lower_padded_char_literal(
    ctx: EmitContext,
    lit: dict,
    sibling: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
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
    width = _field_byte_length(ctx, sibling, materialised, span=span)
    if width is None or width < len(content):
        width = len(content)
    padded = content.ljust(width)
    return ctx.const_to_reg(padded, span=span)


def _lower_relation_node(
    ctx: EmitContext,
    rel: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a structured relation dict {"left": <expr>, "op": "...", "right": <expr>}."""
    left_reg = _lower_relation_operand(
        ctx, rel["left"], rel["right"], materialised, span=span
    )
    right_reg = _lower_relation_operand(
        ctx, rel["right"], rel["left"], materialised, span=span
    )
    op = _OP_MAP.get(rel.get("op", "=="), "==")
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(op),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        ),
        span=span,
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
    *,
    span: SourceSpan | None = None,
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
        ctx.emit_inst(Const.bool_(result, False), span=span)
        return result

    value_reg = _lower_expr_dict(ctx, node.get("operand", {}), materialised, span=span)
    value_str_reg = ctx.emit_to_string(value_reg, span=span)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result,
            func_name=FuncName(builtin),
            args=(Register(str(value_str_reg)),),
        ),
        span=span,
    )
    return result


_SIGN_OP: dict[str, str] = {"POSITIVE": ">", "NEGATIVE": "<", "ZERO": "=="}


def _lower_sign_condition(
    ctx: EmitContext,
    node: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a sign condition {"sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}
    to a boolean: the decoded operand value compared against zero (>0 / <0 / ==0).

    The enclosing ``not`` flag is applied by ``_lower_condition_node`` (the bridge
    folds an inner ``NOT POSITIVE`` into that flag), so this emits the bare
    comparison. An unknown sign never matches rather than evaluating TRUE.
    """
    sign = str(node.get("sign", "")).upper()
    op = _SIGN_OP.get(sign)
    if op is None:
        logger.warning("unknown sign condition %r — never matching", sign)
        result = ctx.fresh_reg()
        ctx.emit_inst(Const.bool_(result, False), span=span)
        return result
    operand_reg = _lower_expr_dict(
        ctx, node.get("operand", {}), materialised, span=span
    )
    zero_reg = ctx.const_to_reg(0, span=span)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(op),
            left=Register(str(operand_reg)),
            right=Register(str(zero_reg)),
        ),
        span=span,
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
    *,
    span: SourceSpan | None = None,
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
        return _unresolvable_operand(ctx, name, span=span)

    subscripts = tuple(expr_from_dict(s) for s in expr.get("subscripts", []))
    ref, rr = ctx.resolve_field_ref(
        name, materialised, subscripts=subscripts, span=span
    )
    full_str_reg = ctx.emit_decode_field_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )

    start_1based_reg = _lower_expr_dict(
        ctx, expr["ref_mod_start"], materialised, span=span
    )
    one_reg = ctx.const_to_reg(1, span=span)
    start_0based_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=start_0based_reg,
            operator=resolve_binop("-"),
            left=Register(str(start_1based_reg)),
            right=Register(str(one_reg)),
        ),
        span=span,
    )

    rm_len = expr.get("ref_mod_length")
    if isinstance(rm_len, dict):
        length_reg = _lower_expr_dict(ctx, rm_len, materialised, span=span)
    else:
        length_reg = ctx.const_to_reg(999999, span=span)

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
        ),
        span=span,
    )
    return sliced_reg


def _unresolvable_operand(
    ctx: EmitContext, name: str, *, span: SourceSpan | None = None
) -> Register:
    """Lower a data-name that is not in the layout.

    The bridge sometimes tags a numeric literal as a ref (an abbreviated-condition
    operand "1"), so try the literal reading first. Anything else is a genuinely
    unresolvable name: emit an obviously-wrong sentinel rather than coercing the
    name to a string literal, so the failure is visible in the log and in the IR.

    Both expression lowerers route here on purpose. They disagreed once — the
    node-based one produced the bare name, and since subscripts lower through that
    path, `TBL-KEY (UNKNOWN-IX)` became string arithmetic yielding a SymbolicValue,
    which compares equal to anything. The divergence was the root cause, not either
    branch, so there is now one policy and one place to change it.
    """
    parsed = ctx.parse_literal(name)
    if isinstance(parsed, (int, float)):
        return ctx.const_to_reg(parsed, span=span)
    logger.warning("unresolvable field reference %r — emitting sentinel", name)
    return ctx.const_to_reg(f"UNRESOLVABLE__{name}", span=span)


def _lower_expr_dict(
    ctx: EmitContext,
    expr: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Recursively lower an expression dict node to a register.

    Supported kinds:
    - {"kind": "ref", "name": "WS-A"} — field reference
    - {"kind": "lit", "value": "10"} — literal constant
    - {"kind": "binop", "op": "+", "left": <expr>, "right": <expr>} — arithmetic
    - {"kind": "neg", "expr": <expr>} — unary negation
    """
    kind = expr.get("kind", "lit")

    if kind == "ref":
        name = expr.get("name", "")
        if "ref_mod_start" in expr:
            return _lower_ref_mod_operand(ctx, expr, materialised, span=span)
        if ctx.has_field(name, materialised):
            subscripts = tuple(expr_from_dict(s) for s in expr.get("subscripts", []))
            ref, rr = ctx.resolve_field_ref(
                name,
                materialised,
                qualifiers=tuple(expr.get("qualifiers", ())),
                subscripts=subscripts,
                span=span,
            )
            return ctx.emit_decode_field(
                rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            )
        return _unresolvable_operand(ctx, name, span=span)

    if kind == "lit":
        raw_val = expr.get("value", "")
        parsed = ctx.parse_literal(raw_val)
        return ctx.const_to_reg(parsed, span=span)

    if kind == "binop":
        left_reg = _lower_expr_dict(ctx, expr["left"], materialised, span=span)
        right_reg = _lower_expr_dict(ctx, expr["right"], materialised, span=span)
        # Preserve the operator; _OP_MAP is identity for its comparison keys, so
        # the only effect of a default-to-"+" here was to silently corrupt every
        # arithmetic "-"/"*"/"/" into "+" (red-dragon-kt70). resolve_binop handles
        # the arithmetic operators directly.
        raw_op = expr.get("op", "+")
        op = _OP_MAP.get(raw_op, raw_op)
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop(op),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            ),
            span=span,
        )
        return result

    if kind == "function":
        # Intrinsic FUNCTION call as a relation operand (red-dragon-ge72), e.g.
        # FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B). Delegate to the shared
        # function-operand lowering so the call + args produce a computed value
        # register that compares normally.
        from interpreter.cobol.lower_arithmetic import lower_function_operand
        from cobol_asg.ref_mod import FunctionCallOperand

        operand = FunctionCallOperand.from_dict(expr)
        return lower_function_operand(ctx, operand, materialised, span=span)

    if kind == "length_of":
        # LENGTH OF <field> as a ref-mod bound: NUMF(1:LENGTH OF N). This
        # dispatcher's unknown-kind fallback is an empty literal, so the bound
        # reached STRING_SLICE as '' and the slice raised. lower_expr_node is
        # the one implementation of the register's constant byte length
        # (red-dragon-twfl).
        return lower_expr_node(ctx, expr_from_dict(expr), materialised, span=span)

    if kind == "neg":
        inner = _lower_expr_dict(ctx, expr["expr"], materialised, span=span)
        zero_reg = ctx.const_to_reg(0, span=span)
        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop("-"),
                left=Register(str(zero_reg)),
                right=Register(str(inner)),
            ),
            span=span,
        )
        return result

    # Unknown kind — treat as empty literal
    return ctx.const_to_reg(ctx.parse_literal(""), span=span)


def _split_condition_subscript(token: str) -> tuple[str, tuple]:
    """Split a (possibly subscripted) condition-name token into its name and
    subscript expression nodes.

    ``"SEL-OK(I)"``   -> ``("SEL-OK", (FieldRefNode("I"),))``
    ``"SEL-OK(1, 2)"``-> ``("SEL-OK", (LiteralNode("1"), FieldRefNode("2")?))``
    ``"SEL-OK"``      -> ``("SEL-OK", ())``

    A bare integer subscript becomes a LiteralNode; anything else becomes a
    FieldRefNode (a simple data-name index). Compound-expression subscripts are
    not parsed here — they are rare in 88 references.
    """
    open_paren = token.find("(")
    if open_paren == -1 or not token.endswith(")"):
        return token, ()
    name = token[:open_paren]
    inner = token[open_paren + 1 : -1]
    subs = tuple(
        (
            LiteralNode(value=s.strip())
            if s.strip().isdigit()
            else FieldRefNode(name=s.strip())
        )
        for s in inner.split(",")
        if s.strip()
    )
    return name, subs


def _lower_condition_str(
    ctx: EmitContext,
    condition: str,
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a flat condition string to a boolean register.

    Supports:
    - "field OP value" where OP is >, <, >=, <=, =, NOT =
    - Single-token condition names (level-88) that expand to parent comparisons,
      including a subscripted reference to a table-defined 88 (``SEL-OK(I)``)
    """
    parts = condition.split()

    if len(parts) == 1:
        name, subscripts = _split_condition_subscript(parts[0])
        if condition_index.has_condition(name):
            return _expand_condition_name(
                ctx,
                name,
                condition_index,
                materialised,
                subscripts=subscripts,
                span=span,
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

        if ctx.has_field(left_name, materialised):
            left_ref, left_rr = ctx.resolve_field_ref(
                left_name, materialised, span=span
            )
            left_reg = ctx.emit_decode_field(
                left_rr,
                left_ref.fl,
                left_ref.offset_reg,
                extent=left_ref.extent,
                span=span,
            )
        else:
            left_reg = ctx.const_to_reg(ctx.parse_literal(left_name), span=span)

        right_parsed = ctx.parse_literal(right_val)
        if isinstance(right_parsed, str) and ctx.has_field(right_parsed, materialised):
            right_ref, right_rr = ctx.resolve_field_ref(
                right_parsed, materialised, span=span
            )
            right_reg = ctx.emit_decode_field(
                right_rr,
                right_ref.fl,
                right_ref.offset_reg,
                extent=right_ref.extent,
                span=span,
            )
        else:
            right_reg = ctx.const_to_reg(right_parsed, span=span)

        result = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result,
                operator=resolve_binop(op),
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
            ),
            span=span,
        )
        return result

    # CLASS/SIGN conditions and other shapes are not yet structured here. An
    # unparseable condition must NOT silently evaluate TRUE — doing so would make
    # whole WHEN/IF branches fire unconditionally. Warn and never-match instead.
    # (Full CLASS/SIGN structuring is deferred — see red-dragon-z31u.)
    logger.warning("unparseable condition %r — never matching", condition)
    result = ctx.fresh_reg()
    ctx.emit_inst(Const.bool_(result, False), span=span)
    return result


_EXACT_OPERATORS = {
    "+": BuiltinName.COBOL_ADD,
    "-": BuiltinName.COBOL_SUBTRACT,
    "*": BuiltinName.COBOL_MULTIPLY,
    "/": BuiltinName.COBOL_DIVIDE,
}


def _float_operand(
    ctx: EmitContext, reg: Register, floating: bool, *, span: SourceSpan | None = None
) -> Register:
    if not floating:
        return reg
    converted = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=converted,
            func_name=FuncName(BuiltinName.COBOL_TO_FLOAT),
            args=(Register(str(reg)),),
        ),
        span=span,
    )
    return converted


def _lower_expr_node_body(
    ctx: EmitContext,
    node: ExprNode,
    materialised: MaterialisedSectionedLayout,
    dmax: int,
    floating: bool,
    field_types,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Walk an expression tree node and emit IR. Returns result register.

    Fixed-point ``BinOpNode``s lower to an exact ``cobol_numeric`` builtin
    truncating to the statically carried decimal places (``node_scale``); a
    floating expression lowers to an ordinary ``Binop`` on IEEE floats, with
    every leaf operand converted through ``__cobol_to_float`` first.
    """
    if isinstance(node, LiteralNode):
        reg = ctx.const_to_reg(ctx.parse_literal(node.value), span=span)
        return _float_operand(ctx, reg, floating, span=span)
    if isinstance(node, FieldRefNode):
        if ctx.has_field(node.name, materialised):
            ref, rr = ctx.resolve_field_ref(
                node.name,
                materialised,
                qualifiers=node.qualifiers,
                subscripts=node.subscripts,
                span=span,
            )
            reg = ctx.emit_decode_field(
                rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            )
            return _float_operand(ctx, reg, floating, span=span)
        return _float_operand(
            ctx, _unresolvable_operand(ctx, node.name, span=span), floating, span=span
        )
    if isinstance(node, BinOpNode):
        left_reg = _lower_expr_node_body(
            ctx, node.left, materialised, dmax, floating, field_types, span=span
        )
        right_reg = _lower_expr_node_body(
            ctx, node.right, materialised, dmax, floating, field_types, span=span
        )
        result_reg = ctx.fresh_reg()
        if floating:
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(node.op),
                    left=Register(str(left_reg)),
                    right=Register(str(right_reg)),
                ),
                span=span,
            )
            return result_reg
        decimals_reg = ctx.const_to_reg(
            node_scale(node, dmax, field_types).decimal_places, span=span
        )
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName(_EXACT_OPERATORS[node.op]),
                args=(Register(str(left_reg)), Register(str(right_reg)), decimals_reg),
            ),
            span=span,
        )
        return result_reg
    if isinstance(node, RefModNode):
        ref, rr = ctx.resolve_field_ref(
            node.name,
            materialised,
            qualifiers=node.qualifiers,
            subscripts=node.subscripts,
            span=span,
        )
        full_str_reg = ctx.emit_decode_field_characters(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
        start_1based_reg = lower_expr_node(
            ctx, node.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        start_0based_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0based_reg,
                operator=resolve_binop("-"),
                left=Register(str(start_1based_reg)),
                right=Register(str(one_reg)),
            ),
            span=span,
        )
        if node.ref_mod_length is not None:
            length_reg = lower_expr_node(
                ctx, node.ref_mod_length, materialised, span=span
            )
        else:
            length_reg = ctx.const_to_reg(999999, span=span)
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
            ),
            span=span,
        )
        # Parse the sliced text as an exact number
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
                args=(Register(str(sliced_reg)),),
            ),
            span=span,
        )
        return _float_operand(ctx, result_reg, floating, span=span)
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
                ctx, expr_to_dict(arg), materialised, span=span
            )
            for arg in node.args
        )
        if builtin is None:
            logger.warning(
                "Unsupported COBOL intrinsic FUNCTION %r — falling back to first argument",
                node.name,
            )
            result_reg = arg_regs[0] if arg_regs else ctx.const_to_reg("", span=span)
            return _float_operand(ctx, result_reg, floating, span=span)
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName(builtin),
                args=arg_regs,
            ),
            span=span,
        )
        return _float_operand(ctx, result_reg, floating, span=span)
    if isinstance(node, FigurativeNode):
        return _float_operand(
            ctx, _lower_figurative_operand(ctx, node, span=span), floating, span=span
        )
    if isinstance(node, LengthOfNode):
        # LENGTH OF <field> is the field's byte length, a compile-time constant
        # and NOT a decode of its value -- the same reading eval_ref_mod_expr
        # gives it inside a ref-mod subscript (red-dragon-oq2c).
        if ctx.has_field(node.name, materialised):
            field_ref, _ = ctx.resolve_field_ref(node.name, materialised, span=span)
            return _float_operand(
                ctx,
                ctx.const_to_reg(field_ref.fl.byte_length, span=span),
                floating,
                span=span,
            )
        logger.warning("LENGTH OF unknown field %s -> 0", node.name)
        return _float_operand(ctx, ctx.const_to_reg(0, span=span), floating, span=span)
    if isinstance(node, DfhRespNode):
        # DFHRESP(<cond>) never reaches lowering when CICS is configured: the
        # condition's number is release-dependent, so the bridge keeps the name
        # and cicada's dfhresp pre-pass rewrites the node to a literal before the
        # expression tree is built. Arriving here means that pre-pass did not
        # run, and there is no number to invent -- guessing one would silently
        # mis-compare every EIBRESP test in the program.
        raise ValueError(
            f"DFHRESP({node.condition}) reached COBOL lowering unresolved: the "
            f"CICS DFHRESP pre-pass did not run. Compile this program through "
            f"the CICS coprocessor, which resolves DFHRESP to its response code."
        )
    logger.warning("Unknown expression node type: %s", type(node).__name__)
    return _float_operand(ctx, ctx.const_to_reg(0, span=span), floating, span=span)


def lower_expr_node(
    ctx: EmitContext,
    node: ExprNode,
    materialised: MaterialisedSectionedLayout,
    receiver_decimals: int = 0,
    floating_receiver: bool = False,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Walk an expression tree and emit IR. Returns the result register.

    Fixed-point expressions follow IBM ARITH(COMPAT): each operator lowers to an
    exact cobol_numeric builtin truncating to its statically carried decimal
    places, with dmax the larger of ``receiver_decimals`` and the non-divisor
    operand decimals. Integer-only division therefore truncates (the mod idiom
    ``A - (A / B) * B``, red-dragon-apoq) while receivers with decimal places
    keep the fraction. An expression with a COMP-1/COMP-2 operand or receiver,
    or a floating intrinsic, is computed in IEEE floating point.
    """

    def field_types(name: str, qualifiers: tuple[str, ...] = ()):
        if not ctx.has_field(name, materialised):
            return None
        return materialised.resolve(name, qualifiers)[0].type_descriptor

    floating = floating_receiver or expression_is_floating(node, field_types)
    dmax = max(receiver_decimals, operand_dmax(node, field_types))
    return _lower_expr_node_body(
        ctx, node, materialised, dmax, floating, field_types, span=span
    )


def _lower_figurative_operand(
    ctx: EmitContext, node: FigurativeNode, *, span: SourceSpan | None = None
) -> Register:
    """A figurative constant used as an expression operand.

    ``COMPUTE WS-PCT = ZEROES`` is the case that matters and the only one with an
    unambiguous arithmetic reading, so the ZERO family becomes the integer 0.

    The other figuratives have no numeric value at all, and this is an
    arithmetic context with no sibling operand to size them against -- unlike
    _figurative_value, which is reached from a comparison and knows the field
    it is being compared to. One fill character is therefore all that can be
    honestly emitted, and it is warned about rather than passed off as correct.
    """
    raw = node.value.upper()
    if raw in ("ZERO", "ZEROS", "ZEROES"):
        return ctx.const_to_reg(0, span=span)
    fill = _FIGURATIVE_FILL.get(raw)
    if fill is None:
        logger.warning("Unknown figurative constant %r -> 0", node.value)
        return ctx.const_to_reg(0, span=span)
    logger.warning(
        "Figurative %r in an arithmetic expression has no length to size it to "
        "-- emitting one %r",
        node.value,
        fill,
    )
    return ctx.const_to_reg(fill, span=span)
