"""Condition lowering — free functions for COBOL condition and expression nodes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import reduce
from typing import TypeGuard

from cobol_asg.cobol_expression import (
    AddressOfNode,
    AllLiteralNode,
    BinOpNode,
    DfhRespNode,
    ExprNode,
    FieldRefNode,
    FigurativeNode,
    FunctionNode,
    LengthOfNode,
    LiteralNode,
    RefModNode,
)
from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.condition import (
    ClassKind,
    ClassTest,
    Combination,
    Condition,
    ConditionNameTest,
    Connective,
    Parenthesised,
    RelationTest,
    SignKind,
    SignTest,
    UnparsedCondition,
    UserClassTest,
)
from cobol_asg.condition_name import ConditionValue
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.ref_mod import FunctionCallOperand, RefModOperand
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
from interpreter.cobol.condition_name_index import ConditionEntry
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


def lower_condition(scope: LoweringScope, node: Condition) -> Register:
    """Lower a condition to a register holding a boolean, recursively walking its
    tree."""
    if isinstance(node, Combination):
        return _lower_combination(scope, node)
    inner = _lower_test(scope, node)
    if not node.negated:
        return inner
    ctx, span = scope.ctx, scope.span
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


def _lower_combination(scope: LoweringScope, node: Combination) -> Register:
    ctx, span = scope.ctx, scope.span
    left_reg = lower_condition(scope, node.left)
    right_reg = lower_condition(scope, node.right)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(
                "and" if node.connective is Connective.AND else "or"
            ),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        ),
        span=span,
    )
    return result


def _lower_test(
    scope: LoweringScope,
    node: (
        RelationTest
        | ConditionNameTest
        | ClassTest
        | UserClassTest
        | SignTest
        | Parenthesised
        | UnparsedCondition
    ),
) -> Register:
    """The test's own truth, before its NOT."""
    match node:
        case ConditionNameTest():
            return _lower_condition_name(scope, node)
        case Parenthesised():
            return lower_condition(scope, node.inner)
        case RelationTest():
            return _lower_relation_node(scope, node)
        case UserClassTest():
            return _lower_user_class(scope, node)
        case ClassTest():
            return _lower_class_condition(scope, node)
        case SignTest():
            return _lower_sign_condition(scope, node)
        case UnparsedCondition():
            return _lower_condition_str(scope, node.text)


def _lower_condition_name(scope: LoweringScope, node: ConditionNameTest) -> Register:
    """An 88-level condition name, a switch-status name, or else the name as text."""
    ctx = scope.ctx
    if ctx.condition_index.has_condition(node.name):
        return _expand_condition_name(
            scope,
            ctx.condition_index.lookup(node.name, node.qualifiers),
            node.subscripts,
        )
    if ctx.switches.has_condition(node.name):
        return _lower_switch_condition(scope, ctx.switches.condition(node.name))
    return _lower_condition_str(scope, node.name)


def _lower_user_class(scope: LoweringScope, node: UserClassTest) -> Register:
    """IS class-name: every character of the operand is in the set the
    SPECIAL-NAMES CLASS clause names."""
    ctx, span = scope.ctx, scope.span
    return emit_all_characters_in(
        scope.emitter,
        ctx.emit_to_string(_lower_operand(scope, node.operand), span=span),
        ctx.const_to_reg(ctx.class_names.characters(node.class_name), span=span),
    )


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


_DEFAULT_FIGURATIVE_LEN = 1


def _field_byte_length(scope: LoweringScope, expr: ExprNode) -> int | None:
    """Return the byte length of a field operand, else None.

    For a reference-modified operand WS-S(start:len) with a literal length, the
    sliced length governs (so a figurative sibling is sized to the slice, not the
    whole field). A non-literal ref-mod length falls back to the full field.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if not isinstance(expr, (FieldRefNode, RefModNode)):
        return None
    if isinstance(expr, RefModNode):
        slice_len = _ref_mod_slice_length(expr)
        if slice_len is not None:
            return slice_len
    if not ctx.has_field(expr.name, materialised):
        return None
    ref, _ = ctx.resolve_field_ref(
        expr.name,
        materialised,
        expr.qualifiers,
        expr.subscripts,
        span=span,
    )
    return ref.fl.byte_length


def _lower_figurative(
    scope: LoweringScope, fig: FigurativeNode, sibling: ExprNode
) -> Register:
    """Lower a figurative constant operand.

    The figurative is materialised as a string literal whose length matches the
    *sibling* operand's field (so it equals the decoded field when the field
    actually holds that figurative). Falls back to a single character when the
    sibling is not a field.
    """
    ctx, span = scope.ctx, scope.span
    value = fig.value.upper()
    # ZERO / ZEROS against a NUMERIC field compares by value (integer 0), not as
    # a zero-filled character string — otherwise "1000.00" <= "0000000000.00"
    # would be a (broken) number-vs-string comparison (red-dragon-z6ad family).
    # NULL is the address 0.
    if value == "NULL" or (
        value in ("ZERO", "ZEROS", "ZEROES") and _is_numeric_field(sibling, scope)
    ):
        return ctx.const_to_reg(0, span=span)
    fill = ctx.figuratives.characters.get(value, " ")
    length = _field_byte_length(scope, sibling)
    if length is None:
        length = _DEFAULT_FIGURATIVE_LEN
    literal = fill * length
    return ctx.const_to_reg(literal, span=span)


def _lower_all_literal(
    scope: LoweringScope, node: AllLiteralNode, sibling: ExprNode
) -> Register:
    ctx, span = scope.ctx, scope.span
    pattern = literal_characters(node.literal)
    length = _field_byte_length(scope, sibling)
    width = len(pattern) if length is None else length
    return ctx.const_to_reg(repeat_to_width(pattern, width), span=span)


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


def _is_alphanumeric_operand(expr: ExprNode) -> bool:
    """True if an operand is alphanumeric (character) data by its kind alone.

    Covers an alphanumeric figurative (SPACES / LOW-VALUES / HIGH-VALUES /
    QUOTES — not numeric ZEROS), ALL literal, and a quoted non-numeric character
    literal (e.g. '*'). A numeric literal (e.g. 11) is NOT alphanumeric.
    Determined structurally from the operand — no source-text sniffing.
    """
    match expr:
        case FigurativeNode():
            return expr.value.upper() in _ALPHANUMERIC_FIGURATIVES
        case AllLiteralNode():
            return True
        case LiteralNode():
            return not expr.numeric
        case _:
            return False


def _is_numeric_field(expr: ExprNode, scope: LoweringScope) -> TypeGuard[FieldRefNode]:
    """True if an operand is a reference to a numeric field (zoned / COMP-3 /
    binary / float). A reference-modified operand is a character slice, excluded.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if not isinstance(expr, FieldRefNode):
        return False
    if not ctx.has_field(expr.name, materialised):
        return False
    ref, _ = ctx.resolve_field_ref(expr.name, materialised, expr.qualifiers, span=span)
    return ref.fl.type_descriptor.is_numeric


def _is_nonnumeric_operand(scope: LoweringScope, expr: ExprNode) -> bool:
    ctx, materialised = scope.ctx, scope.materialised
    if _is_alphanumeric_operand(expr) or isinstance(expr, RefModNode):
        return True
    return (
        isinstance(expr, FieldRefNode)
        and ctx.has_field(expr.name, materialised)
        and not _is_numeric_field(expr, scope)
    )


def _lower_relation_operand(
    scope: LoweringScope, expr: ExprNode, sibling: ExprNode
) -> Register:
    match expr:
        case FigurativeNode():
            return _lower_figurative(scope, expr, sibling)
        case AllLiteralNode():
            return _lower_all_literal(scope, expr, sibling)
        case _:
            return _lower_operand(scope, expr)


def _lower_numeric_field_characters(
    scope: LoweringScope, expr: FieldRefNode
) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    ref, rr = ctx.resolve_field_ref(
        expr.name,
        materialised,
        qualifiers=expr.qualifiers,
        subscripts=expr.subscripts,
        span=span,
    )
    return emit_field_digit_image(scope.emitter, rr, ref)


def _lower_nonnumeric_operand(
    scope: LoweringScope, expr: ExprNode, sibling: ExprNode
) -> Register:
    ctx, span = scope.ctx, scope.span
    if isinstance(expr, LiteralNode) and not _is_alphanumeric_operand(expr):
        return ctx.const_to_reg(expr.value.lstrip("+-"), span=span)
    if _is_numeric_field(expr, scope):
        return _lower_numeric_field_characters(scope, expr)
    return _lower_relation_operand(scope, expr, sibling)


def _lower_relation_registers(
    scope: LoweringScope, rel: RelationTest
) -> tuple[Register, Register]:
    ctx, span = scope.ctx, scope.span
    left, right = rel.left, rel.right
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


def _lower_relation_node(scope: LoweringScope, rel: RelationTest) -> Register:
    """Lower a relation test: left operand, operator, right operand."""
    ctx, span = scope.ctx, scope.span
    left_reg, right_reg = _lower_relation_registers(scope, rel)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(rel.operator.value),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        ),
        span=span,
    )
    return result


_CLASS_BUILTIN: Mapping[ClassKind, str] = {
    ClassKind.NUMERIC: BuiltinName.IS_NUMERIC,
    ClassKind.ALPHABETIC: BuiltinName.IS_ALPHABETIC,
    ClassKind.ALPHABETIC_LOWER: BuiltinName.IS_ALPHABETIC_LOWER,
    ClassKind.ALPHABETIC_UPPER: BuiltinName.IS_ALPHABETIC_UPPER,
}


def _lower_class_condition(scope: LoweringScope, node: ClassTest) -> Register:
    """Lower a class condition to a boolean.

    The operand's decoded value is converted to character data and passed to the
    matching COBOL-layer class-test builtin (__is_numeric / __is_alphabetic / ...).
    """
    if node.kind is ClassKind.NUMERIC:
        return _lower_numeric_class(scope, node.operand)
    return _lower_class_builtin(scope, node.kind, node.operand)


def _lower_numeric_class(scope: LoweringScope, operand: ExprNode) -> Register:
    if _is_numeric_field(operand, scope):
        return _lower_numeric_item_class(scope, operand)
    if _is_nonnumeric_operand(scope, operand):
        return emit_is_digits(
            scope.emitter,
            scope.ctx.emit_to_string(_lower_operand(scope, operand), span=scope.span),
        )
    return _lower_class_builtin(scope, ClassKind.NUMERIC, operand)


def _lower_class_builtin(
    scope: LoweringScope, kind: ClassKind, operand: ExprNode
) -> Register:
    e = scope.emitter
    return e.call(
        _CLASS_BUILTIN[kind],
        e.ctx.emit_to_string(_lower_operand(scope, operand), span=e.span),
    )


def _lower_numeric_item_class(scope: LoweringScope, expr: FieldRefNode) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    ref, rr = ctx.resolve_field_ref(
        expr.name,
        materialised,
        qualifiers=expr.qualifiers,
        subscripts=expr.subscripts,
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


_SIGN_OP: Mapping[SignKind, str] = {
    SignKind.POSITIVE: ">",
    SignKind.NEGATIVE: "<",
    SignKind.ZERO: "==",
}


def _lower_sign_condition(scope: LoweringScope, node: SignTest) -> Register:
    """Lower a sign condition to a boolean: the decoded operand value compared
    against zero (>0 / <0 / ==0).

    The test's NOT is applied by ``lower_condition`` (the bridge folds an inner
    ``NOT POSITIVE`` into it), so this emits the bare comparison.
    """
    ctx, span = scope.ctx, scope.span
    operand_reg = _lower_operand(scope, node.operand)
    zero_reg = ctx.const_to_reg(0, span=span)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(_SIGN_OP[node.kind]),
            left=Register(str(operand_reg)),
            right=Register(str(zero_reg)),
        ),
        span=span,
    )
    return result


def _ref_mod_slice_length(expr: RefModNode) -> int | None:
    """Return the static slice length of a ref-mod operand, if it is a literal."""
    if not isinstance(expr.ref_mod_length, LiteralNode):
        return None
    try:
        return int(expr.ref_mod_length.value)
    except ValueError:
        return None


def _lower_ref_mod_operand(scope: LoweringScope, expr: RefModNode) -> Register:
    """Lower a reference-modified field operand WS-S(start:length) in a condition.

    Decodes the underlying field to its character string and slices it with the
    1-based start (converted to 0-based) and optional length. The start and
    length are re-evaluated each call, so a loop variable subscript reflects the
    current iteration. Returns a string-valued register so it compares correctly
    against figurative/string siblings.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if not ctx.has_field(expr.name, materialised):
        return _unresolvable_operand(scope, expr.name)

    ref, rr = ctx.resolve_field_ref(
        expr.name,
        materialised,
        qualifiers=expr.qualifiers,
        subscripts=expr.subscripts,
        span=span,
    )
    full_str_reg = ctx.emit_decode_field_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )

    start_1based_reg = _lower_operand(scope, expr.ref_mod_start)
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

    if expr.ref_mod_length is not None:
        length_reg = _lower_operand(scope, expr.ref_mod_length)
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


def _lower_field_ref(scope: LoweringScope, expr: FieldRefNode) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if not ctx.has_field(expr.name, materialised):
        return _unresolvable_operand(scope, expr.name)
    ref, rr = ctx.resolve_field_ref(
        expr.name,
        materialised,
        qualifiers=expr.qualifiers,
        subscripts=expr.subscripts,
        span=span,
    )
    return ctx.emit_decode_field(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )


def _lower_binop_operand(scope: LoweringScope, expr: BinOpNode) -> Register:
    ctx, span = scope.ctx, scope.span
    left_reg = _lower_operand(scope, expr.left)
    right_reg = _lower_operand(scope, expr.right)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(expr.op),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        ),
        span=span,
    )
    return result


def _lower_operand(scope: LoweringScope, expr: ExprNode) -> Register:
    """Lower a condition operand to a register.

    Unlike :func:`lower_expr_node`, arithmetic is an ordinary ``Binop`` and a
    reference-modified operand stays character data. A figurative constant, an
    ALL literal or a DFHRESP reached here outside a relation lower to the empty
    literal.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    match expr:
        case FieldRefNode():
            return _lower_field_ref(scope, expr)
        case RefModNode():
            return _lower_ref_mod_operand(scope, expr)
        case LiteralNode():
            return ctx.const_to_reg(ctx.parse_literal(expr.value), span=span)
        case AddressOfNode():
            return PointerLowering(ctx, materialised, span).address_of(
                expr.name, expr.qualifiers, expr.subscripts
            )
        case BinOpNode():
            return _lower_binop_operand(scope, expr)
        case FunctionNode():
            # Intrinsic FUNCTION call as a relation operand (red-dragon-ge72).
            from interpreter.cobol.lower_arithmetic import lower_function_operand

            operand = FunctionCallOperand(name=expr.name, args=expr.args)
            return lower_function_operand(ctx, operand, materialised, span=span)
        case LengthOfNode():
            # LENGTH OF <field> as a ref-mod bound: NUMF(1:LENGTH OF N)
            # (red-dragon-twfl).
            return lower_expr_node(scope, expr)
        case _:
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


def _lower_condition_str(scope: LoweringScope, condition: str) -> Register:
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
        if ctx.condition_index.has_condition(name):
            return _expand_condition_name(
                scope, ctx.condition_index.lookup(name), subscripts
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
        start_1based_reg = lower_expr_node(scope, node.ref_mod_start)
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
            length_reg = lower_expr_node(scope, node.ref_mod_length)
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
            FunctionCallOperand(name=node.name, args=node.args),
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


_NO_RECEIVER = ArithmeticPrecision(dmax=0, floating=False)


def lower_expr_node(
    scope: LoweringScope, node: ExprNode, receiver: ArithmeticPrecision = _NO_RECEIVER
) -> Register:
    """Walk an expression tree and emit IR. Returns the result register.

    Fixed-point expressions follow IBM ARITH(COMPAT): each operator lowers to an
    exact cobol_numeric builtin truncating to its statically carried decimal
    places, with dmax the larger of the receiver's decimals and the non-divisor
    operand decimals. Integer-only division therefore truncates (the mod idiom
    ``A - (A / B) * B``, red-dragon-apoq) while receivers with decimal places
    keep the fraction. An expression with a COMP-1/COMP-2 operand or receiver,
    or a floating intrinsic, is computed in IEEE floating point.
    """
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
