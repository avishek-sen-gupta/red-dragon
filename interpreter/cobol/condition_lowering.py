"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from functools import reduce

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
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.ref_mod import FunctionCallOperand, RefModOperand
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.arithmetic_precision import ArithmeticPrecision
from interpreter.cobol.arithmetic_scale import (
    FieldTypes,
    expression_is_floating,
    node_scale,
    operand_dmax,
)
from interpreter.cobol.class_test_ir import (
    emit_all_characters_in,
    emit_is_digits,
    emit_packed_is_numeric,
    emit_zoned_is_numeric,
)
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_name_index import ConditionEntry, ConditionNameIndex
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.digit_image_ir import emit_field_digit_image
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.figurative_constants import repeat_to_width
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.pointer_lowering import PointerLowering
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.switch_condition import SwitchCondition
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction, Const
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register

logger = logging.getLogger(__name__)


def _emit_88_value_reg(
    e: IrEmitter, value: str, figurative: bool, parent: FieldLayout
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
    if figurative and value.upper() in e.ctx.figuratives.characters:
        return _figurative_88_value(e, value.upper(), parent)
    if parent.type_descriptor.holds_characters:
        padded = value.ljust(max(parent.byte_length, len(value)))
        return e.ctx.const_to_reg(padded, span=e.span)
    return e.ctx.const_to_reg(e.ctx.parse_literal(value), span=e.span)


def _figurative_88_value(e: IrEmitter, name: str, parent: FieldLayout) -> Register:
    """ZERO on a numeric parent is the number 0; any other figurative constant is
    its character repeated to the parent's size."""
    if not parent.type_descriptor.holds_characters and name in _ZERO_NAMES:
        return e.ctx.const_to_reg(0, span=e.span)
    fill = e.ctx.figuratives.characters[name] * max(parent.byte_length, 1)
    return e.ctx.const_to_reg(fill, span=e.span)


_ZERO_NAMES = frozenset({"ZERO", "ZEROS", "ZEROES"})


def _emit_single_value_test(
    scope: LoweringScope,
    cv: ConditionValue,
    parent: RefModOperand,
    subscripts: tuple = (),
) -> Register:
    """Emit IR to test a parent field against a single ConditionValue.

    For discrete values: parent_field == value
    For THRU ranges: parent_field >= from AND parent_field <= to

    ``subscripts`` selects the OCCURS element when the level-88 is defined on a
    table item and referenced with a subscript (e.g. ``SEL-OK(I)``).
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    parent_ref, parent_rr = ctx.resolve_field_ref(
        parent.name,
        materialised,
        parent.qualifiers,
        subscripts=subscripts,
        span=span,
    )
    parent_reg = ctx.emit_decode_field(
        parent_rr,
        parent_ref.fl,
        parent_ref.offset_reg,
        extent=parent_ref.extent,
        span=span,
    )

    if cv.is_range:
        from_reg = _emit_88_value_reg(
            scope.emitter, cv.from_val, cv.figurative, parent_ref.fl
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
            parent.name,
            materialised,
            parent.qualifiers,
            subscripts=subscripts,
            span=span,
        )
        parent_reg2 = ctx.emit_decode_field(
            parent_rr2,
            parent_ref2.fl,
            parent_ref2.offset_reg,
            extent=parent_ref2.extent,
            span=span,
        )
        to_reg = _emit_88_value_reg(
            scope.emitter, cv.to_val, cv.figurative, parent_ref.fl
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
        scope.emitter, cv.from_val, cv.figurative, parent_ref.fl
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


def _emit_or_chain(scope: LoweringScope, regs: list[Register]) -> Register:
    """Combine a list of boolean registers with OR. Returns result register."""
    return reduce(
        lambda acc, reg: _emit_or(scope, acc, reg),
        regs[1:],
        regs[0],
    )


def _emit_or(scope: LoweringScope, left_reg: Register, right_reg: Register) -> Register:
    """Emit a single OR between two boolean registers."""
    ctx, span = scope.ctx, scope.span
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
    scope: LoweringScope, entry: ConditionEntry, subscripts: tuple[ExprNode, ...]
) -> Register:
    """Expand a level-88 condition name's declaration into field comparison IR.

    For single-value conditions: parent == value
    For multi-value: parent == v1 OR parent == v2 OR ...
    For THRU ranges: parent >= from AND parent <= to
    Mixed: combines all with OR.

    ``subscripts`` selects the OCCURS element for a table-defined 88
    (e.g. ``SEL-OK(I)``).
    """
    ctx, span = scope.ctx, scope.span
    value_regs = [
        _emit_single_value_test(scope, cv, entry.parent, subscripts=subscripts)
        for cv in entry.values
    ]

    if not value_regs:
        result = ctx.fresh_reg()
        ctx.emit_inst(Const.bool_(result, True), span=span)
        return result

    return _emit_or_chain(scope, value_regs)


_NO_CONDITION_NAMES = ConditionNameIndex({})


def lower_condition(
    ctx: EmitContext,
    condition: dict,
    materialised: MaterialisedSectionedLayout,
    condition_index: ConditionNameIndex = _NO_CONDITION_NAMES,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower a structured condition dict to a register holding a boolean."""
    return _lower_condition_node(
        LoweringScope(ctx, materialised, span), condition, condition_index
    )


def _lower_condition_node(
    scope: LoweringScope, node: dict, condition_index: ConditionNameIndex
) -> Register:
    """Recursively walk a structured condition dict node and emit IR."""
    ctx, span = scope.ctx, scope.span
    if "op" in node:
        # Compound: {"op": "AND"/"OR", "left": {...}, "right": {...}}
        op = node["op"]
        left_reg = _lower_condition_node(scope, node["left"], condition_index)
        right_reg = _lower_condition_node(scope, node["right"], condition_index)
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
                scope,
                condition_index.lookup(
                    name, tuple(node.get("condition_qualifiers", ()))
                ),
                subscripts,
            )
        elif ctx.switches.has_condition(name):
            inner = _lower_switch_condition(scope, ctx.switches.condition(name))
        else:
            # Fall back to string lowering for unresolved names
            inner = _lower_condition_str(scope, name, condition_index)
    elif "condition" in node:
        # Nested parenthesised condition
        inner = _lower_condition_node(scope, node["condition"], condition_index)
    elif "relation" in node:
        # Structured relation: {"left": <expr>, "op": "...", "right": <expr>}
        inner = _lower_relation_node(scope, node["relation"])
    elif "class_name" in node:
        # IS class-name: every character of the operand is in the set the
        # SPECIAL-NAMES CLASS clause names.
        inner = emit_all_characters_in(
            scope.emitter,
            ctx.emit_to_string(
                _lower_expr_dict(scope, node["operand"]),
                span=span,
            ),
            ctx.const_to_reg(ctx.class_names.characters(node["class_name"]), span=span),
        )
    elif "class" in node:
        # Class condition: {"class": "NUMERIC"|"ALPHABETIC"|..., "operand": <expr>}
        inner = _lower_class_condition(scope, node)
    elif "sign" in node:
        # Sign condition: {"sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}
        inner = _lower_sign_condition(scope, node)
    else:
        # Fallback: flat text (CLASS/SIGN conditions, EVALUATE/SEARCH callers)
        inner = _lower_condition_str(scope, node.get("text", ""), condition_index)

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


def _lower_switch_condition(
    scope: LoweringScope, condition: SwitchCondition
) -> Register:
    """A switch-status condition: the run's status of the switch, compared with
    the status the condition-name stands for."""
    ctx, span = scope.ctx, scope.span
    status = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status,
            func_name=FuncName("__cobol_switch_status"),
            args=(ctx.const_to_reg(condition.environment_name, span=span),),
        ),
        span=span,
    )
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop("=="),
            left=status,
            right=ctx.const_to_reg(condition.status.value, span=span),
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


_DEFAULT_FIGURATIVE_LEN = 1


def _field_byte_length(scope: LoweringScope, expr: dict) -> int | None:
    """Return the byte length of a {"kind":"ref"} field operand, else None.

    For a reference-modified operand WS-S(start:len) with a literal length, the
    sliced length governs (so a figurative sibling is sized to the slice, not the
    whole field). A non-literal ref-mod length falls back to the full field.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if expr.get("kind") == "ref":
        if "ref_mod_start" in expr:
            slice_len = _ref_mod_slice_length(expr)
            if slice_len is not None:
                return slice_len
        name = expr.get("name", "")
        if ctx.has_field(name, materialised):
            ref, _ = ctx.resolve_field_ref(
                name,
                materialised,
                tuple(expr.get("qualifiers", ())),
                tuple(expr_from_dict(s) for s in expr.get("subscripts", [])),
                span=span,
            )
            return ref.fl.byte_length
    return None


def _lower_figurative(scope: LoweringScope, fig: dict, sibling: dict) -> Register:
    """Lower a {"kind":"figurative","value":...} operand.

    The figurative is materialised as a string literal whose length matches the
    *sibling* operand's field (so it equals the decoded field when the field
    actually holds that figurative). Falls back to a single character when the
    sibling is not a field.
    """
    ctx, span = scope.ctx, scope.span
    value = str(fig.get("value", "")).upper()
    if value == _ALL:
        return _lower_all_literal(scope, fig, sibling)
    # ZERO / ZEROS against a NUMERIC field compares by value (integer 0), not as
    # a zero-filled character string — otherwise "1000.00" <= "0000000000.00"
    # would be a (broken) number-vs-string comparison (red-dragon-z6ad family).
    # NULL is the address 0.
    if value == "NULL" or (
        value in ("ZERO", "ZEROS", "ZEROES") and _is_numeric_field(scope, sibling)
    ):
        return ctx.const_to_reg(0, span=span)
    fill = ctx.figuratives.characters.get(value, " ")
    length = _field_byte_length(scope, sibling)
    if length is None:
        length = _DEFAULT_FIGURATIVE_LEN
    literal = fill * length
    return ctx.const_to_reg(literal, span=span)


def _lower_all_literal(scope: LoweringScope, fig: dict, sibling: dict) -> Register:
    ctx, span = scope.ctx, scope.span
    pattern = literal_characters(str(fig.get("literal", "")))
    length = _field_byte_length(scope, sibling)
    width = len(pattern) if length is None else length
    return ctx.const_to_reg(repeat_to_width(pattern, width), span=span)


_ALL = "ALL"

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
        _ALL,
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
    return kind == "lit" and not expr.get("numeric", False)


def _is_numeric_field(scope: LoweringScope, expr: dict) -> bool:
    """True if an operand is a reference to a numeric field (zoned / COMP-3 /
    binary / float). A reference-modified operand is a character slice, excluded.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if expr.get("kind") != "ref" or "ref_mod_start" in expr:
        return False
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return False
    ref, _ = ctx.resolve_field_ref(
        name, materialised, tuple(expr.get("qualifiers", ())), span=span
    )
    return ref.fl.type_descriptor.is_numeric


def _is_nonnumeric_operand(scope: LoweringScope, expr: dict) -> bool:
    ctx, materialised = scope.ctx, scope.materialised
    if _is_alphanumeric_operand(expr) or "ref_mod_start" in expr:
        return True
    return (
        expr.get("kind") == "ref"
        and ctx.has_field(expr.get("name", ""), materialised)
        and not _is_numeric_field(scope, expr)
    )


def _lower_relation_operand(
    scope: LoweringScope, expr: dict, sibling: dict
) -> Register:
    if expr.get("kind") == "figurative":
        return _lower_figurative(scope, expr, sibling)
    return _lower_expr_dict(scope, expr)


def _lower_numeric_field_characters(scope: LoweringScope, expr: dict) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    ref, rr = ctx.resolve_field_ref(
        expr.get("name", ""),
        materialised,
        qualifiers=tuple(expr.get("qualifiers", ())),
        subscripts=tuple(expr_from_dict(s) for s in expr.get("subscripts", [])),
        span=span,
    )
    return emit_field_digit_image(scope.emitter, rr, ref)


def _lower_nonnumeric_operand(
    scope: LoweringScope, expr: dict, sibling: dict
) -> Register:
    ctx, span = scope.ctx, scope.span
    if expr.get("kind") == "lit" and not _is_alphanumeric_operand(expr):
        return ctx.const_to_reg(str(expr.get("value", "")).lstrip("+-"), span=span)
    if _is_numeric_field(scope, expr):
        return _lower_numeric_field_characters(scope, expr)
    return _lower_relation_operand(scope, expr, sibling)


def _lower_relation_registers(
    scope: LoweringScope, rel: dict
) -> tuple[Register, Register]:
    ctx, span = scope.ctx, scope.span
    left, right = rel["left"], rel["right"]
    if not any(_is_nonnumeric_operand(scope, e) for e in (left, right)):
        return (
            _lower_relation_operand(scope, left, right),
            _lower_relation_operand(scope, right, left),
        )
    left_reg = _lower_nonnumeric_operand(scope, left, right)
    right_reg = _lower_nonnumeric_operand(scope, right, left)
    return (
        _in_collating_order(scope, ctx.emit_pad_to(left_reg, right_reg, span=span)),
        _in_collating_order(scope, ctx.emit_pad_to(right_reg, left_reg, span=span)),
    )


def _in_collating_order(scope: LoweringScope, value: Register) -> Register:
    """The characters of a nonnumeric operand as their positions in the program
    collating sequence, so that comparing them compares in that sequence."""
    ctx, span = scope.ctx, scope.span
    native, positions = ctx.collating_sequence.ordinal_alphabets()
    ordered = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=ordered,
            func_name=FuncName(BuiltinName.STRING_CONVERT),
            args=(
                value,
                ctx.const_to_reg(native, span=span),
                ctx.const_to_reg(positions, span=span),
            ),
        ),
        span=span,
    )
    return ordered


def _lower_relation_node(scope: LoweringScope, rel: dict) -> Register:
    """Lower a structured relation dict {"left": <expr>, "op": "...", "right": <expr>}."""
    ctx, span = scope.ctx, scope.span
    left_reg, right_reg = _lower_relation_registers(scope, rel)
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


def _lower_class_condition(scope: LoweringScope, node: dict) -> Register:
    """Lower a class condition {"class": <NAME>, "operand": <expr>} to a boolean.

    The operand's decoded value is converted to character data and passed to the
    matching COBOL-layer class-test builtin (__is_numeric / __is_alphabetic / ...).
    An unknown class never matches (rather than silently evaluating TRUE).
    """
    class_name = str(node.get("class", "")).upper()
    operand = node.get("operand", {})
    if class_name == "NUMERIC":
        return _lower_numeric_class(scope, operand)
    return _lower_class_builtin(scope, class_name, operand)


def _lower_numeric_class(scope: LoweringScope, operand: dict) -> Register:
    if _is_numeric_field(scope, operand):
        return _lower_numeric_item_class(scope, operand)
    if _is_nonnumeric_operand(scope, operand):
        return emit_is_digits(
            scope.emitter,
            scope.ctx.emit_to_string(_lower_expr_dict(scope, operand), span=scope.span),
        )
    return _lower_class_builtin(scope, "NUMERIC", operand)


def _lower_class_builtin(
    scope: LoweringScope, class_name: str, operand: dict
) -> Register:
    e = scope.emitter
    builtin = _CLASS_BUILTIN.get(class_name, "")
    if not builtin:
        logger.warning("unknown class condition %r — never matching", class_name)
        return e.bool_(False)
    return e.call(
        builtin,
        e.ctx.emit_to_string(_lower_expr_dict(scope, operand), span=e.span),
    )


def _lower_numeric_item_class(scope: LoweringScope, expr: dict) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    ref, rr = ctx.resolve_field_ref(
        expr.get("name", ""),
        materialised,
        qualifiers=tuple(expr.get("qualifiers", ())),
        subscripts=tuple(expr_from_dict(s) for s in expr.get("subscripts", [])),
        span=span,
    )
    td = ref.fl.type_descriptor
    if td.category not in _STORED_CLASS_TESTS:
        return ctx.emit_decoded_is_numeric(rr, ref, span=span)
    e = scope.emitter
    stored = ctx.emit_load_field_bytes(rr, ref, span=span)
    if td.category == CobolDataCategory.COMP3:
        return emit_packed_is_numeric(e, stored, td, ref.fl.byte_length)
    return emit_zoned_is_numeric(e, stored, ref.fl)


_STORED_CLASS_TESTS = frozenset(
    {CobolDataCategory.ZONED_DECIMAL, CobolDataCategory.COMP3}
)


_SIGN_OP: dict[str, str] = {"POSITIVE": ">", "NEGATIVE": "<", "ZERO": "=="}


def _lower_sign_condition(scope: LoweringScope, node: dict) -> Register:
    """Lower a sign condition {"sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}
    to a boolean: the decoded operand value compared against zero (>0 / <0 / ==0).

    The enclosing ``not`` flag is applied by ``_lower_condition_node`` (the bridge
    folds an inner ``NOT POSITIVE`` into that flag), so this emits the bare
    comparison. An unknown sign never matches rather than evaluating TRUE.
    """
    ctx, span = scope.ctx, scope.span
    sign = str(node.get("sign", "")).upper()
    op = _SIGN_OP.get(sign)
    if op is None:
        logger.warning("unknown sign condition %r — never matching", sign)
        result = ctx.fresh_reg()
        ctx.emit_inst(Const.bool_(result, False), span=span)
        return result
    operand_reg = _lower_expr_dict(scope, node.get("operand", {}))
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


def _lower_ref_mod_operand(scope: LoweringScope, expr: dict) -> Register:
    """Lower a reference-modified field operand WS-S(start:length) in a condition.

    Decodes the underlying field to its character string and slices it with the
    1-based start (converted to 0-based) and optional length. The start and
    length are themselves expression dicts (re-evaluated each call, so a loop
    variable subscript reflects the current iteration). Returns a string-valued
    register so it compares correctly against figurative/string siblings.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    name = expr.get("name", "")
    if not ctx.has_field(name, materialised):
        return _unresolvable_operand(scope, name)

    subscripts = tuple(expr_from_dict(s) for s in expr.get("subscripts", []))
    ref, rr = ctx.resolve_field_ref(
        name,
        materialised,
        qualifiers=tuple(expr.get("qualifiers", ())),
        subscripts=subscripts,
        span=span,
    )
    full_str_reg = ctx.emit_decode_field_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )

    start_1based_reg = _lower_expr_dict(scope, expr["ref_mod_start"])
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
        length_reg = _lower_expr_dict(scope, rm_len)
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


def _unresolvable_operand(scope: LoweringScope, name: str) -> Register:
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
    ctx, span = scope.ctx, scope.span
    parsed = ctx.parse_literal(name)
    if isinstance(parsed, (int, float)):
        return ctx.const_to_reg(parsed, span=span)
    logger.warning("unresolvable field reference %r — emitting sentinel", name)
    return ctx.const_to_reg(f"UNRESOLVABLE__{name}", span=span)


def _lower_expr_dict(scope: LoweringScope, expr: dict) -> Register:
    """Recursively lower an expression dict node to a register.

    Supported kinds:
    - {"kind": "ref", "name": "WS-A"} — field reference
    - {"kind": "lit", "value": "10"} — literal constant
    - {"kind": "binop", "op": "+", "left": <expr>, "right": <expr>} — arithmetic
    - {"kind": "neg", "expr": <expr>} — unary negation
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    kind = expr.get("kind", "lit")

    if kind == "ref":
        name = expr.get("name", "")
        if "ref_mod_start" in expr:
            return _lower_ref_mod_operand(scope, expr)
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
        return _unresolvable_operand(scope, name)

    if kind == "lit":
        raw_val = expr.get("value", "")
        parsed = ctx.parse_literal(raw_val)
        return ctx.const_to_reg(parsed, span=span)

    if kind == "address_of":
        return PointerLowering(ctx, materialised, span).address_of(
            expr["name"], expr.get("qualifiers", ()), expr.get("subscripts", ())
        )

    if kind == "binop":
        left_reg = _lower_expr_dict(scope, expr["left"])
        right_reg = _lower_expr_dict(scope, expr["right"])
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

        operand = FunctionCallOperand.from_dict(expr)
        return lower_function_operand(ctx, operand, materialised, span=span)

    if kind == "length_of":
        # LENGTH OF <field> as a ref-mod bound: NUMF(1:LENGTH OF N). This
        # dispatcher's unknown-kind fallback is an empty literal, so the bound
        # reached STRING_SLICE as '' and the slice raised. lower_expr_node is
        # the one implementation of the register's constant byte length
        # (red-dragon-twfl).
        return _lower_expression(scope, expr_from_dict(expr), _NO_RECEIVER)

    if kind == "neg":
        inner = _lower_expr_dict(scope, expr["expr"])
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
    scope: LoweringScope, condition: str, condition_index: ConditionNameIndex
) -> Register:
    """Lower a flat condition string to a boolean register.

    Supports:
    - "field OP value" where OP is >, <, >=, <=, =, NOT =
    - Single-token condition names (level-88) that expand to parent comparisons,
      including a subscripted reference to a table-defined 88 (``SEL-OK(I)``)
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    parts = condition.split()

    if len(parts) == 1:
        name, subscripts = _split_condition_subscript(parts[0])
        if condition_index.has_condition(name):
            return _expand_condition_name(
                scope, condition_index.lookup(name), subscripts
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


def _float_operand(scope: LoweringScope, reg: Register, floating: bool) -> Register:
    ctx, span = scope.ctx, scope.span
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
    scope: LoweringScope,
    node: ExprNode,
    precision: ArithmeticPrecision,
    field_types,
) -> Register:
    """Walk an expression tree node and emit IR. Returns result register.

    Fixed-point ``BinOpNode``s lower to an exact ``cobol_numeric`` builtin
    truncating to the statically carried decimal places (``node_scale``); a
    floating expression lowers to an ordinary ``Binop`` on IEEE floats, with
    every leaf operand converted through ``__cobol_to_float`` first.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    floating = precision.floating
    if isinstance(node, LiteralNode):
        reg = ctx.const_to_reg(ctx.parse_literal(node.value), span=span)
        return _float_operand(scope, reg, floating)
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
            return _float_operand(scope, reg, floating)
        return _float_operand(scope, _unresolvable_operand(scope, node.name), floating)
    if isinstance(node, BinOpNode):
        left_reg = _lower_expr_node_body(scope, node.left, precision, field_types)
        right_reg = _lower_expr_node_body(scope, node.right, precision, field_types)
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
            node_scale(node, precision.dmax, field_types).decimal_places, span=span
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
        start_1based_reg = _lower_expression(scope, node.ref_mod_start, _NO_RECEIVER)
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
            length_reg = _lower_expression(scope, node.ref_mod_length, _NO_RECEIVER)
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
        return _float_operand(scope, result_reg, floating)
    if isinstance(node, FunctionNode):
        # Intrinsic FUNCTION call as an expression/relation operand (e.g.
        # FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B), or COMPUTE X =
        # FUNCTION TRIM(WS-A)). Each arg is lowered to a string-valued register
        # then passed to the COBOL-layer builtin (red-dragon-ge72).
        from interpreter.cobol.lower_arithmetic import lower_function_in_expression

        result_reg = lower_function_in_expression(
            scope,
            FunctionCallOperand(
                name=node.name, args=tuple(expr_to_dict(arg) for arg in node.args)
            ),
            precision,
        )
        return _float_operand(scope, result_reg, floating)
    if isinstance(node, FigurativeNode):
        return _float_operand(scope, _lower_figurative_operand(scope, node), floating)
    if isinstance(node, LengthOfNode):
        if ctx.has_field(node.name, materialised):
            return _float_operand(
                scope,
                ctx.emit_length_of(node.name, materialised, node.qualifiers, span=span),
                floating,
            )
        logger.warning("LENGTH OF unknown field %s -> 0", node.name)
        return _float_operand(scope, ctx.const_to_reg(0, span=span), floating)
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
    return _float_operand(scope, ctx.const_to_reg(0, span=span), floating)


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
    return _lower_expression(
        LoweringScope(ctx, materialised, span),
        node,
        ArithmeticPrecision(dmax=receiver_decimals, floating=floating_receiver),
    )


_NO_RECEIVER = ArithmeticPrecision(dmax=0, floating=False)


def _lower_expression(
    scope: LoweringScope, node: ExprNode, receiver: ArithmeticPrecision
) -> Register:
    field_types = _field_types(scope.ctx, scope.materialised)
    floating = receiver.floating or expression_is_floating(node, field_types)
    dmax = max(receiver.dmax, operand_dmax(node, field_types))
    return _lower_expr_node_body(
        scope, node, ArithmeticPrecision(dmax=dmax, floating=floating), field_types
    )


def _field_types(
    ctx: EmitContext, materialised: MaterialisedSectionedLayout
) -> FieldTypes:
    def field_types(name: str, qualifiers: tuple[str, ...] = ()):
        if not ctx.has_field(name, materialised):
            return None
        return materialised.resolve(name, qualifiers)[0].type_descriptor

    return field_types


def standalone_precision(
    ctx: EmitContext, node: ExprNode, materialised: MaterialisedSectionedLayout
) -> ArithmeticPrecision:
    field_types = _field_types(ctx, materialised)
    return ArithmeticPrecision(
        dmax=operand_dmax(node, field_types),
        floating=expression_is_floating(node, field_types),
    )


def _lower_figurative_operand(scope: LoweringScope, node: FigurativeNode) -> Register:
    """A figurative constant used as an expression operand.

    ``COMPUTE WS-PCT = ZEROES`` is the case that matters and the only one with an
    unambiguous arithmetic reading, so the ZERO family becomes the integer 0.

    The other figuratives have no numeric value at all, and this is an
    arithmetic context with no sibling operand to size them against -- unlike
    _figurative_value, which is reached from a comparison and knows the field
    it is being compared to. One fill character is therefore all that can be
    honestly emitted, and it is warned about rather than passed off as correct.
    """
    ctx, span = scope.ctx, scope.span
    raw = node.value.upper()
    if raw in ("ZERO", "ZEROS", "ZEROES"):
        return ctx.const_to_reg(0, span=span)
    fill = ctx.figuratives.characters.get(raw)
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
