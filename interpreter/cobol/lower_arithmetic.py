"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from functools import partial, reduce

from cobol_asg.cobol_expression import expr_from_dict
from cobol_asg.cobol_statements import (
    ArithmeticCorrespondingStatement,
    ArithmeticStatement,
    CobolStatementType,
    ComputedGoto,
    ComputeStatement,
    ComputeTarget,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitProgramStatement,
    ExitStatement,
    GobackStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    MoveCorrespondingStatement,
    MoveStatement,
    NextSentenceStatement,
    SetStatement,
    SimpleGoto,
    StopRunStatement,
    WhenOtherStatement,
    WhenStatement,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.exit_kind import ExitKind
from cobol_asg.ref_mod import (
    FunctionCallOperand,
    RefModBinOp,
    RefModExpr,
    RefModFunction,
    RefModLengthOf,
    RefModLiteral,
    RefModOperand,
    RefModReference,
)
from cobol_asg.source_span import SourceSpan
from cobol_memory.region_id import RegionId
from cobol_numeric.number import from_literal
from cobol_numeric.scale import (
    Scale,
    add_scale,
    carry,
    div_scale,
    literal_scale,
    mul_scale,
)
from interpreter.cobol.arithmetic_receiver import ArithmeticReceiver
from interpreter.cobol.arithmetic_scale import (
    field_scale,
    is_floating_type,
    receiver_capacity,
    receiver_rounding_places,
)
from interpreter.cobol.arithmetic_scale import receiver_decimals as _receiver_decimals
from interpreter.cobol.arithmetic_value import ArithmeticValue
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_lowering import (
    _float_operand,
    _lower_condition_str,
    lower_expr_node,
)
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.field_resolution import ResolvedFieldRef, whole_field_extent
from interpreter.cobol.figurative_constants import (
    COBOL_FIGURATIVE_CONSTANTS,
    raw_figurative_byte,
    translate_cobol_figurative,
)
from interpreter.cobol.lower_pointer import is_pointer_set, lower_pointer_set
from interpreter.cobol.lower_program_exit import (
    emit_publish_run_unit_return_code,
    emit_return_code_load,
    lower_program_exit,
)
from interpreter.cobol.run_unit import RANDOM_STATE, RUN_UNIT_LAYOUT, RUN_UNIT_VAR
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Halt_,
    Label_,
    LoadVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind, resolve_binop
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)

# COBOL special registers the ProLeap bridge does not model as DATA DIVISION
# fields. A MOVE into one of these surfaces with an unresolved/null operand name
# (the bridge's placeholder), so we recognise both forms here.
_SPECIAL_REGISTER_NAMES = frozenset(
    {
        # RETURN-CODE removed (red-dragon-o8uq): it now resolves to a dedicated SR
        # region and lowers via the ordinary encode→WRITE_REGION MOVE path.
        "SORT-RETURN",
        "TALLY",
        "name=[null]",  # bridge placeholder for an unmodelled register operand
    }
)


def _is_special_register(name: str) -> bool:
    """True if ``name`` is an unmodelled COBOL special register (MOVE target)."""
    return str(name).upper() in {n.upper() for n in _SPECIAL_REGISTER_NAMES}


ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}

_EXACT_VERB_BUILTINS = {
    "ADD": BuiltinName.COBOL_ADD,
    "SUBTRACT": BuiltinName.COBOL_SUBTRACT,
    "MULTIPLY": BuiltinName.COBOL_MULTIPLY,
    "DIVIDE": BuiltinName.COBOL_DIVIDE,
}


def _operand_type(
    ctx: EmitContext, operand: RefModOperand, materialised: MaterialisedSectionedLayout
):
    if not ctx.has_field(operand.name, materialised):
        return None
    return materialised.resolve(operand.name, operand.qualifiers)[0].type_descriptor


def _operand_scale(
    ctx: EmitContext, operand: RefModOperand, materialised: MaterialisedSectionedLayout
) -> Scale:
    name = operand.name
    td = _operand_type(ctx, operand, materialised)
    if td is not None:
        return field_scale(td)
    try:
        from_literal(translate_cobol_figurative(name))
    except ValueError:
        return Scale(1, 0)
    return literal_scale(translate_cobol_figurative(name))


_VERB_SCALES: Mapping[str, Callable[[Scale, Scale, int], Scale]] = {
    "ADD": lambda left, right, _dmax: add_scale(left, right),
    "SUBTRACT": lambda left, right, _dmax: add_scale(left, right),
    "MULTIPLY": lambda left, right, _dmax: mul_scale(left, right),
    "DIVIDE": div_scale,
}


def _is_floating_operand(
    ctx: EmitContext, operand: RefModOperand, materialised: MaterialisedSectionedLayout
) -> bool:
    return ctx.has_field(operand.name, materialised) and is_floating_type(
        materialised.resolve(operand.name, operand.qualifiers)[0].type_descriptor
    )


def _receiver_places(
    ctx: EmitContext,
    receivers: Sequence[RefModOperand],
    materialised: MaterialisedSectionedLayout,
) -> int:
    return max(
        (
            _receiver_decimals(
                materialised.resolve(r.name, r.qualifiers)[0].type_descriptor,
                r.rounded,
            )
            for r in receivers
            if ctx.has_field(r.name, materialised)
        ),
        default=0,
    )


def _operand_value(
    ctx: EmitContext,
    operand: RefModOperand,
    register: Register,
    materialised: MaterialisedSectionedLayout,
) -> ArithmeticValue:
    return ArithmeticValue(
        register=register,
        scale=_operand_scale(ctx, operand, materialised),
        floating=_is_floating_operand(ctx, operand, materialised),
    )


def _emit_float_operation(
    ctx: EmitContext,
    op: str,
    left: ArithmeticValue,
    right: ArithmeticValue,
    scale: Scale,
    *,
    span: SourceSpan | None = None,
) -> ArithmeticValue:
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(ARITHMETIC_OPS[op]),
            left=_float_operand(ctx, left.register, True, span=span),
            right=_float_operand(ctx, right.register, True, span=span),
        ),
        span=span,
    )
    return ArithmeticValue(register=result_reg, scale=scale, floating=True)


def _emit_verb_operation(
    ctx: EmitContext,
    op: str,
    left: ArithmeticValue,
    right: ArithmeticValue,
    receivers: Sequence[RefModOperand],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> ArithmeticValue:
    """Emit ``left <op> right``, exact unless IBM's floating-point rule applies."""
    operand_places = (
        left.scale.decimal_places
        if op == "DIVIDE"
        else max(left.scale.decimal_places, right.scale.decimal_places)
    )
    dmax = max(_receiver_places(ctx, receivers, materialised), operand_places)
    scale = carry(_VERB_SCALES[op](left.scale, right.scale, dmax), dmax)
    if (
        left.floating
        or right.floating
        or any(_is_floating_operand(ctx, r, materialised) for r in receivers)
    ):
        return _emit_float_operation(ctx, op, left, right, scale, span=span)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(_EXACT_VERB_BUILTINS[op]),
            args=(
                left.register,
                right.register,
                ctx.const_to_reg(scale.decimal_places, span=span),
            ),
        ),
        span=span,
    )
    return ArithmeticValue(register=result_reg, scale=scale, floating=False)


def _compute_overflow_flag(
    ctx: EmitContext,
    result_reg: Register,
    td: CobolTypeDescriptor,
    *,
    span: SourceSpan | None = None,
) -> Register:
    overflow_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=overflow_reg,
            func_name=FuncName(BuiltinName.COBOL_SIZE_ERROR),
            args=(result_reg, ctx.const_to_reg(receiver_capacity(td), span=span)),
        ),
        span=span,
    )
    return overflow_reg


def eval_ref_mod_expr(
    ctx: EmitContext,
    expr: RefModExpr,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Evaluate a reference modification expression to an IR register.

    Handles three cases:
    - RefModLiteral: numeric literal → Const → register
    - RefModReference: data item name → resolve field → decode → to_string → register
    - RefModBinOp: binary operation → evaluate left/right → emit Binop → register
    """
    if isinstance(expr, RefModLiteral):
        # Literal: numeric value for reference modification.
        # parse_literal converts e.g. "2" → int 2 so arithmetic Binops work.
        return ctx.const_to_reg(ctx.parse_literal(expr.value), span=span)

    elif isinstance(expr, RefModReference):
        # Field reference: resolve field → decode
        # Return the decoded numeric value (don't convert to string)
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, rr = ctx.resolve_field_ref(
                name, materialised, qualifiers=expr.qualifiers, span=span
            )
            decoded_reg = ctx.emit_decode_field(
                rr,
                field_ref.fl,
                field_ref.offset_reg,
                extent=field_ref.extent,
                span=span,
            )
            # Return the decoded numeric value directly
            return decoded_reg
        else:
            # Unknown field: treat as literal numeric 0
            return ctx.const_to_reg(0, span=span)

    elif isinstance(expr, RefModLengthOf):
        # LENGTH OF <field>: the field's byte length (a compile-time constant),
        # NOT a decode of its value. Used in ref-mod start/length expressions
        # such as DEST(LENGTH OF G + 1 : LENGTH OF H) (red-dragon-oq2c).
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
            return ctx.const_to_reg(field_ref.fl.byte_length, span=span)
        logging.warning("eval_ref_mod_expr: LENGTH OF unknown field %s → 0", name)
        return ctx.const_to_reg(0, span=span)

    elif isinstance(expr, RefModFunction):
        # An intrinsic FUNCTION computing a bound: M(1:FUNCTION LENGTH(M)). The
        # call is the bound, never the operand — the operand serializer used to
        # return it in place of the whole sliced reference (red-dragon-pe45).
        return lower_function_operand(
            ctx,
            FunctionCallOperand(name=expr.name, args=expr.args),
            materialised,
            span=span,
        )

    elif isinstance(expr, RefModBinOp):
        # Binary operation: evaluate left and right, emit Binop
        left_reg = eval_ref_mod_expr(ctx, expr.left, materialised, span=span)
        right_reg = eval_ref_mod_expr(ctx, expr.right, materialised, span=span)
        result_reg = ctx.fresh_reg()

        op_str = expr.op
        binop_kind = resolve_binop(op_str)

        ctx.emit_inst(
            Binop(
                operator=binop_kind,
                left=left_reg,
                right=right_reg,
                result_reg=result_reg,
            ),
            span=span,
        )
        return result_reg

    else:
        # Fallback: treat as literal zero
        return ctx.const_to_reg(0, span=span)


# Maps canonical COBOL intrinsic function names to COBOL-layer builtin names.
_INTRINSIC_FUNCTIONS = {
    "UPPER-CASE": BuiltinName.UPPER_CASE,
    "LOWER-CASE": BuiltinName.LOWER_CASE,
    "TRIM": BuiltinName.TRIM,
    "CURRENT-DATE": BuiltinName.CURRENT_DATE,
    "LENGTH": BuiltinName.LENGTH,
    "NUMVAL": BuiltinName.NUMVAL,
    "NUMVAL-C": BuiltinName.NUMVAL_C,
    "TEST-NUMVAL": BuiltinName.TEST_NUMVAL,
    "TEST-NUMVAL-C": BuiltinName.TEST_NUMVAL_C,
    "INTEGER-OF-DATE": BuiltinName.INTEGER_OF_DATE,
    "DATE-OF-INTEGER": BuiltinName.DATE_OF_INTEGER,
    "MOD": BuiltinName.MOD,
    "REVERSE": BuiltinName.REVERSE,
    "MAX": BuiltinName.MAX,
    "MIN": BuiltinName.MIN,
    "SUM": BuiltinName.SUM,
    "ABS": BuiltinName.ABS,
    "SQRT": BuiltinName.SQRT,
    "SIN": BuiltinName.SIN,
    "COS": BuiltinName.COS,
    "TAN": BuiltinName.TAN,
    "ASIN": BuiltinName.ASIN,
    "ACOS": BuiltinName.ACOS,
    "ATAN": BuiltinName.ATAN,
    "RANGE": BuiltinName.RANGE,
    "MEAN": BuiltinName.MEAN,
    "MEDIAN": BuiltinName.MEDIAN,
    "MIDRANGE": BuiltinName.MIDRANGE,
    "VARIANCE": BuiltinName.VARIANCE,
    "ORD-MAX": BuiltinName.ORD_MAX,
    "ORD-MIN": BuiltinName.ORD_MIN,
    "CONCATENATE": BuiltinName.CONCATENATE,
    "EXP": BuiltinName.EXP,
    "LOG": BuiltinName.LOG,
    "FACTORIAL": BuiltinName.FACTORIAL,
    "INTEGER": BuiltinName.INTEGER,
    "INTEGER-PART": BuiltinName.INTEGER_PART,
    "FRACTION-PART": BuiltinName.FRACTION_PART,
    "REM": BuiltinName.REM,
    "SUBSTITUTE": BuiltinName.SUBSTITUTE,
    "EXP10": BuiltinName.EXP10,
    "LOG10": BuiltinName.LOG10,
    "CHAR": BuiltinName.CHAR,
    "ORD": BuiltinName.ORD,
    "DAY-OF-INTEGER": BuiltinName.DAY_OF_INTEGER,
    "INTEGER-OF-DAY": BuiltinName.INTEGER_OF_DAY,
    "ANNUITY": BuiltinName.ANNUITY,
    "PRESENT-VALUE": BuiltinName.PRESENT_VALUE,
    "DATE-TO-YYYYMMDD": BuiltinName.DATE_TO_YYYYMMDD,
    "DAY-TO-YYYYDDD": BuiltinName.DAY_TO_YYYYDDD,
    "YEAR-TO-YYYY": BuiltinName.YEAR_TO_YYYY,
}


def _lower_function_arg_to_string(
    ctx: EmitContext,
    arg: dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower one intrinsic-function argument dict to a string-valued register.

    Field references are decoded then stringified (intrinsics like UPPER-CASE
    operate on character data); literals are parsed as constants.
    """
    kind = arg.get("kind", "lit")
    if kind == "ref":
        # Delegated rather than re-resolved: this path used to call
        # resolve_field_ref with neither the subscripts nor the reference
        # modification the node carries, so FUNCTION f(TBL(I)) always read
        # occurrence 1 (red-dragon-jscx). _lower_expr_dict is the one place that
        # decodes a structured ref, and it honours both.
        from interpreter.cobol.condition_lowering import (
            _lower_expr_dict,
            _unresolvable_operand,
        )

        name = arg.get("name", "")
        if not ctx.has_field(name, materialised):
            return _unresolvable_operand(ctx, name, span=span)
        decoded = _lower_expr_dict(ctx, arg, materialised, span=span)
        return ctx.emit_to_string(decoded, span=span)
    if kind == "lit":
        return ctx.const_to_reg(ctx.parse_literal(arg.get("value", "")), span=span)
    # Arithmetic / other expression args: lower via the expression path, then
    # stringify so the builtin (e.g. UPPER-CASE) receives character data.
    from interpreter.cobol.condition_lowering import _lower_expr_dict

    value_reg = _lower_expr_dict(ctx, arg, materialised, span=span)
    return ctx.emit_to_string(value_reg, span=span)


def lower_function_operand(
    ctx: EmitContext,
    operand: FunctionCallOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower an intrinsic FUNCTION call operand to a value register.

    Recognised functions (UPPER-CASE, LOWER-CASE, CURRENT-DATE) are emitted as a
    CallFunction against the COBOL-layer builtins. Unknown functions log a warning
    and fall back to their first argument (or empty string) — never silent wrong data.
    FUNCTION RANDOM keeps its state in the run-unit region, so it lowers on its own.
    """
    lowering = _STATEFUL_FUNCTIONS.get(operand.name.upper(), _lower_builtin_function)
    return lowering(ctx, operand, materialised, span=span)


def _lower_builtin_function(
    ctx: EmitContext,
    operand: FunctionCallOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    builtin = _INTRINSIC_FUNCTIONS.get(operand.name.upper())
    if builtin is None:
        logger.warning(
            "Unsupported COBOL intrinsic FUNCTION %r — falling back to first argument",
            operand.name,
        )
        if operand.args:
            return _lower_function_arg_to_string(
                ctx, operand.args[0], materialised, span=span
            )
        return ctx.const_to_reg("", span=span)

    arg_regs = tuple(
        _lower_function_arg_to_string(ctx, arg, materialised, span=span)
        for arg in operand.args
    )
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(builtin),
            args=arg_regs,
        ),
        span=span,
    )
    return result_reg


def _lower_random(
    ctx: EmitContext,
    operand: FunctionCallOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """FUNCTION RANDOM [(seed)]: load the run unit's generator state, step it,
    store it back, and return its value -- one sequence for the whole run unit."""
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    extent = whole_field_extent(fl, RegionId.RUN_UNIT)
    region_reg, state_reg = ctx.fresh_reg(), ctx.fresh_reg()
    offset_reg = ctx.const_to_reg(fl.offset, span=span)
    ctx.emit_inst(LoadVar(result_reg=region_reg, name=RUN_UNIT_VAR), span=span)
    ctx._emit_load_region(
        result_reg=state_reg,
        region_reg=region_reg,
        offset_reg=offset_reg,
        length=fl.byte_length,
        extent=extent,
        span=span,
    )
    seed_regs = tuple(
        _lower_function_arg_to_string(ctx, arg, materialised, span=span)
        for arg in operand.args[:1]
    )
    next_reg = _call_builtin(
        ctx, BuiltinName.RANDOM_NEXT_STATE, (state_reg, *seed_regs), span=span
    )
    ctx._emit_write_region(
        region_reg=region_reg,
        offset_reg=offset_reg,
        value_reg=next_reg,
        length=fl.byte_length,
        extent=extent,
        span=span,
    )
    return _call_builtin(ctx, BuiltinName.RANDOM_VALUE, (next_reg,), span=span)


def _call_builtin(
    ctx: EmitContext,
    builtin: str,
    args: tuple[Register, ...],
    *,
    span: SourceSpan | None,
) -> Register:
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=result_reg, func_name=FuncName(builtin), args=args),
        span=span,
    )
    return result_reg


_STATEFUL_FUNCTIONS = {"RANDOM": _lower_random}


def lower_move(
    ctx: EmitContext,
    stmt: MoveStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MOVE X [( start : length )] TO Y...Z.

    The source is evaluated ONCE and stored into every receiving field, each with
    its own reference modification and PICTURE conversion (COBOL semantics).
    """
    span = stmt.span

    # Intrinsic FUNCTION source (e.g. FUNCTION UPPER-CASE(...)): evaluate to a
    # value register, then distribute to every receiving field. Functions carry
    # no source-side reference modification, so the ref-mod block is skipped.
    if isinstance(stmt.source, FunctionCallOperand):
        source_value_reg = lower_function_operand(
            ctx, stmt.source, materialised, span=span
        )
        for target in stmt.targets:
            _store_move_value(ctx, target, source_value_reg, materialised, span=span)
        return

    # LENGTH OF <field> source: the field's byte length (a compile-time constant
    # numeric value), distributed to every receiver. CardDemo CSUTLDTC uses
    # `MOVE LENGTH OF LS-DATE TO VSTRING-LENGTH` to set the ODO length before the
    # CEEDAYS CALL (red-dragon). Mirrors the ref-mod LENGTH OF handling above.
    if stmt.source.length_of:
        name = stmt.source.length_of
        if ctx.has_field(name, materialised):
            field_ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
            length_value = field_ref.fl.byte_length
        else:
            logger.warning("MOVE LENGTH OF unknown field %r — using 0", name)
            length_value = 0
        source_value_reg = ctx.const_to_reg(length_value, span=span)
        for target in stmt.targets:
            _store_move_value(ctx, target, source_value_reg, materialised, span=span)
        return

    # Raw figurative source (HIGH-VALUES / LOW-VALUES): these denote raw bytes —
    # 0xFF / 0x00 in every receiver position, whatever its category — so they
    # skip the character path, which converts per the receiving PICTURE and
    # would turn a numeric receiver into a number (red-dragon-raxa).
    # Each receiver's whole width is filled with the raw byte. A reference-modified
    # source slice still selects bytes, so it keeps the character path below; a
    # reference-modified TARGET likewise needs the splice path and is excluded here.
    if (
        not ctx.has_field(stmt.source.name, materialised)
        and stmt.source.ref_mod_start is None
    ):
        fill_byte = raw_figurative_byte(stmt.source.name)
        if fill_byte is not None:
            for target in stmt.targets:
                if not ctx.has_field(target.name, materialised):
                    if _is_special_register(target.name):
                        logger.warning(
                            "MOVE into special register %r is not modelled — skipping",
                            target.name,
                        )
                    continue
                if target.ref_mod_start is not None:
                    # Ref-modified receiver: fall back to the character path so the
                    # SPLICE write still works (rare combination).
                    raw_str = chr(fill_byte)
                    src_reg = ctx.const_to_reg(raw_str, span=span)
                    _store_move_value(ctx, target, src_reg, materialised, span=span)
                    continue
                target_ref, target_rr = ctx.resolve_field_ref(
                    target.name,
                    materialised,
                    target.qualifiers,
                    subscripts=target.subscripts,
                    span=span,
                )
                ctx.emit_fill_raw_byte(
                    target_rr,
                    target_ref.fl,
                    fill_byte,
                    target_ref.offset_reg,
                    extent=target_ref.extent,
                    span=span,
                )
            return

    # Resolve the source field once (when it is a field). A numeric-DISPLAY
    # (zoned) source carries an extra character representation, picked per target
    # by category-pair in _store_move_value (red-dragon-0fqr).
    # Track whether the source is a figurative constant — see per-target loop.
    _figurative_fill_char: str | None = None
    source_fl: FieldLayout | None = None
    # Get the source value (decode field or literal) — evaluated ONCE.
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(
            stmt.source.name,
            materialised,
            stmt.source.qualifiers,
            subscripts=stmt.source.subscripts,
            span=span,
        )
        source_fl = source_ref.fl
        # A ref-modified source is sliced as characters, so it must start from the
        # field's character image; without one, a numeric-DISPLAY source is sliced
        # at offsets that have slid left (red-dragon-wlms). An unmodified source
        # keeps the decoded-value reading, which _store_move_value converts per
        # receiving category.
        if stmt.source.ref_mod_start is not None:
            value_str_reg = ctx.emit_decode_field_characters(
                source_rr,
                source_ref.fl,
                source_ref.offset_reg,
                extent=source_ref.extent,
                span=span,
            )
        else:
            decoded_reg = ctx.emit_decode_field(
                source_rr,
                source_ref.fl,
                source_ref.offset_reg,
                extent=source_ref.extent,
                span=span,
            )
            value_str_reg = ctx.emit_to_string(decoded_reg, span=span)
    else:
        literal = strip_cobol_literal(translate_cobol_figurative(stmt.source.name))
        value_str_reg = ctx.const_to_reg(literal, span=span)
        # COBOL figurative constants (SPACES/ZEROS/ZEROES/QUOTES) fill ALL
        # receiver positions with the same character — MOVE ZEROES TO X(3)
        # produces '000', not '0  '. Track the fill char here; the per-target
        # loop repeats it to the target's width before encoding.
        # HIGH-VALUES/LOW-VALUES are already handled by the raw-byte path above.
        # Only applies when no source reference modification is present.
        if stmt.source.ref_mod_start is None:
            _figurative_fill_char = COBOL_FIGURATIVE_CONSTANTS.get(
                stmt.source.name.upper()
            )

    # Handle reference modification if present
    if stmt.source.ref_mod_start is not None:
        # Evaluate start and length expressions
        start_reg = eval_ref_mod_expr(
            ctx, stmt.source.ref_mod_start, materialised, span=span
        )
        # COBOL uses 1-indexed positions, but SLICE uses 0-indexed.
        # Convert: start_0indexed = start_1indexed - 1
        one_reg = ctx.const_to_reg(1, span=span)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=start_reg,
                right=one_reg,
                result_reg=start_0indexed_reg,
            ),
            span=span,
        )

        if stmt.source.ref_mod_length is not None:
            # Both start and length specified: SLICE operation
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised, span=span
            )
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, length_reg),
                ),
                span=span,
            )
            value_str_reg = result_reg
        else:
            # Only start specified, no length: SLICE from start to end
            # Use a large sentinel as length to get the substring to end.
            large_length = ctx.const_to_reg(999999, span=span)
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, large_length),
                ),
                span=span,
            )
            value_str_reg = result_reg

    # For a numeric-DISPLAY (zoned) source with NO source reference modification,
    # compute its zoned character representation ONCE (width-preserving digit
    # characters). _store_move_value uses this only for alphanumeric receivers,
    # where COBOL moves the sending field's characters left-justified rather than
    # the numeric value (red-dragon-0fqr). Ref-modified sources keep the existing
    # sliced-string path.
    zoned_display_reg: Register = NO_REGISTER
    if (
        source_fl is not None
        and stmt.source.ref_mod_start is None
        and source_fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL
    ):
        zoned_display_reg = ctx.emit_decode_zoned_display(
            source_rr,
            source_fl,
            source_ref.offset_reg,
            extent=source_ref.extent,
            span=span,
        )

    # Store the (once-evaluated) source value into each receiving field. Each
    # target gets its own reference modification and PICTURE conversion; the
    # base source value (source_value_reg) is never clobbered across targets.
    source_value_reg = value_str_reg
    for target in stmt.targets:
        if not ctx.has_field(target.name, materialised) and _is_special_register(
            target.name
        ):
            logger.warning(
                "MOVE into special register %r is not modelled — skipping", target.name
            )
            continue
        # Figurative constants fill ALL receiver positions with the same character.
        # MOVE ZEROES TO PIC X(3) → '000', not '0  '.  Build a target-width
        # repeated string at compile time (constant folding) and use it instead of
        # the single-character source for this target only.  Only applies when
        # there is no target reference modification (a ref-mod write targets a
        # specific slice, so the fill character must remain single for SPLICE).
        effective_source = source_value_reg
        if _figurative_fill_char is not None and target.ref_mod_start is None:
            if ctx.has_field(target.name, materialised):
                tgt_ref, _ = ctx.resolve_field_ref(
                    target.name, materialised, target.qualifiers, span=span
                )
                fill_width = tgt_ref.fl.byte_length
                filled = ctx.const_to_reg(_figurative_fill_char * fill_width, span=span)
                effective_source = filled
        _store_move_value(
            ctx, target, effective_source, materialised, zoned_display_reg, span=span
        )


def _store_move_value(
    ctx: EmitContext,
    target: RefModOperand,
    source_value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    zoned_display_reg: Register = NO_REGISTER,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Store an already-evaluated MOVE source value into one receiving field.

    Applies the target's own reference modification (SPLICE write path) and
    PICTURE conversion. The source value register is never clobbered.

    When the source is a numeric-DISPLAY (zoned) field and this receiver is
    alphanumeric, COBOL moves the sending field's CHARACTER representation
    (zoned digit characters, width-preserving) left-justified — NOT the numeric
    value. zoned_display_reg carries that character form; it is used only for
    alphanumeric receivers without target reference modification (red-dragon-0fqr).
    """
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name,
        materialised,
        target.qualifiers,
        subscripts=target.subscripts,
        span=span,
    )

    if (
        zoned_display_reg.is_present()
        and target.ref_mod_start is None
        and target_ref.fl.type_descriptor.holds_characters
    ):
        source_value_reg = zoned_display_reg

    target_value_reg = source_value_reg

    # Handle target reference modification (write path): MOVE X TO Y(start:length)
    if target.ref_mod_start is not None:
        # Load current target field value as string (needed for SPLICE)
        target_decoded = ctx.emit_decode_field(
            target_rr,
            target_ref.fl,
            target_ref.offset_reg,
            extent=target_ref.extent,
            span=span,
        )
        target_str_reg = ctx.emit_to_string(target_decoded, span=span)

        # Evaluate target ref mod start; convert 1-indexed → 0-indexed
        tgt_start_reg = eval_ref_mod_expr(
            ctx, target.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_start_reg,
                right=one_reg,
                result_reg=tgt_start_0indexed_reg,
            ),
            span=span,
        )

        # Evaluate target ref mod length (or use large sentinel for "to end")
        if target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(
                ctx, target.ref_mod_length, materialised, span=span
            )
        else:
            tgt_length_reg = ctx.const_to_reg(999999, span=span)

        # Emit SPLICE: replace substring in target with source value
        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    target_str_reg,
                    tgt_start_0indexed_reg,
                    tgt_length_reg,
                    source_value_reg,
                ),
            ),
            span=span,
        )
        target_value_reg = spliced_reg

    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl,
        target_value_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def lower_move_corresponding(
    ctx: EmitContext,
    stmt: MoveCorrespondingStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MOVE CORRESPONDING src TO dst — copy matching direct leaf fields, each
    group found in whichever section declares it."""
    span = stmt.span
    src_group, src_rr, src_region = _require_group(stmt.source, materialised)

    for target_name in stmt.targets:
        dst_group, dst_rr, dst_region = _require_group(target_name, materialised)
        for name in src_group.fields.keys() & dst_group.fields.keys():
            src_fl = src_group.fields[name]
            dst_fl = dst_group.fields[name]
            src_ref = ctx.resolve_field_ref_from(
                src_fl, src_rr, src_region, materialised, span=span
            )
            decoded = ctx.emit_decode_field(
                src_rr, src_fl, src_ref.offset_reg, extent=src_ref.extent, span=span
            )
            dst_ref = ctx.resolve_field_ref_from(
                dst_fl, dst_rr, dst_region, materialised, span=span
            )
            ctx.emit_encode_and_write(
                dst_rr,
                dst_fl,
                ctx.emit_to_string(decoded, span=span),
                dst_ref.offset_reg,
                extent=dst_ref.extent,
                span=span,
            )


def _require_group(
    name: str, materialised: MaterialisedSectionedLayout
) -> tuple[DataLayout, Register, RegionId]:
    found = _find_group_and_reg(name, materialised)
    if found is None:
        raise LookupError(f"Group not found in any section: {name!r}")
    return found


def _find_group_and_reg(
    name: str, materialised: MaterialisedSectionedLayout
) -> tuple[DataLayout, Register, RegionId] | None:
    """Return (group DataLayout, region Register, RegionId) for the group, or None.

    The RegionId is carried out alongside the register because the caller
    builds field extents from the group's FieldLayouts, and an extent is only
    comparable against another within the same region buffer.
    """
    for layout, reg, region in (
        (*materialised.local_storage, RegionId.LOCAL_STORAGE),
        (*materialised.working_storage, RegionId.WORKING_STORAGE),
        (*materialised.linkage, RegionId.LINKAGE),
        (*materialised.file, RegionId.FILE),
    ):
        try:
            grp = layout.lookup_group(name)
            return grp, _group_region(grp, reg, region, materialised), region
        except KeyError:
            pass
    return None


def _group_region(
    grp: DataLayout,
    section_reg: Register,
    region: RegionId,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """A LINKAGE group lives in its own 01's argument, not one section region. A
    group with no leaf of its own has nothing CORRESPONDING reads or writes."""
    if region is not RegionId.LINKAGE or not grp.fields:
        return section_reg
    return materialised.linkage_binding(next(iter(grp.fields.values()))).region_reg


def lower_arithmetic_corresponding(
    ctx: EmitContext,
    stmt: ArithmeticCorrespondingStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT CORRESPONDING src TO/FROM dst.

    For each field name present in both src and dst groups, emit the
    equivalent of ADD src.field TO dst.field (or SUBTRACT).
    """
    span = stmt.span
    op_str = "+" if stmt.op == "ADD" else "-"

    src_result = _find_group_and_reg(stmt.source, materialised)
    dst_result = _find_group_and_reg(stmt.target, materialised)

    if src_result is None or dst_result is None:
        return

    src_group, src_rr, src_region = src_result
    dst_group, dst_rr, dst_region = dst_result

    matching_names = src_group.fields.keys() & dst_group.fields.keys()
    for name in matching_names:
        src_fl = src_group.fields[name]
        dst_fl = dst_group.fields[name]

        src_ref = ctx.resolve_field_ref_from(
            src_fl, src_rr, src_region, materialised, span=span
        )
        src_val = ctx.emit_decode_field(
            src_rr, src_fl, src_ref.offset_reg, extent=src_ref.extent, span=span
        )

        dst_ref = ctx.resolve_field_ref_from(
            dst_fl, dst_rr, dst_region, materialised, span=span
        )
        dst_val = ctx.emit_decode_field(
            dst_rr, dst_fl, dst_ref.offset_reg, extent=dst_ref.extent, span=span
        )

        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(op_str),
                left=Register(str(dst_val)),
                right=Register(str(src_val)),
            ),
            span=span,
        )
        result_str = ctx.emit_to_string(result_reg, span=span)
        ctx.emit_encode_and_write(
            dst_rr,
            dst_fl,
            result_str,
            dst_ref.offset_reg,
            extent=dst_ref.extent,
            span=span,
        )


def _emit_arithmetic_writeback(
    ctx: EmitContext,
    target_op: RefModOperand,
    target_ref: ResolvedFieldRef,
    target_rr: Register,
    result_str_reg: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Write arithmetic result into target, applying target ref-mod if present.

    Plain write: encode result_str_reg into the target field.
    Ref-mod write (ARITHMETIC TARGET REF-MOD): decode existing target value,
    splice the result string into the requested substring position, then encode
    and write back the spliced whole — identical to the MOVE target ref-mod path.
    """
    fl = target_ref.fl
    offset_reg = target_ref.offset_reg

    if target_op.ref_mod_start is not None:
        target_decoded = ctx.emit_decode_field(
            target_rr, fl, offset_reg, extent=target_ref.extent, span=span
        )
        target_str_reg = ctx.emit_to_string(target_decoded, span=span)

        tgt_start_reg = eval_ref_mod_expr(
            ctx, target_op.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_start_reg,
                right=one_reg,
                result_reg=tgt_start_0indexed_reg,
            ),
            span=span,
        )

        if target_op.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(
                ctx, target_op.ref_mod_length, materialised, span=span
            )
        else:
            tgt_length_reg = ctx.const_to_reg(999999, span=span)

        # Parse the text as an exact number, then normalise → int → zero-padded
        # string ('015') before splicing to fill the exact ref-mod width.
        parsed_norm = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=parsed_norm,
                func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
                args=(result_str_reg,),
            ),
            span=span,
        )
        int_norm = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=int_norm, func_name=FuncName("int"), args=(parsed_norm,)
            ),
            span=span,
        )
        int_str_reg = ctx.emit_to_string(int_norm, span=span)
        padded_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=padded_reg,
                func_name=FuncName(BuiltinName.STRING_ZFILL),
                args=(int_str_reg, tgt_length_reg),
            ),
            span=span,
        )

        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    target_str_reg,
                    tgt_start_0indexed_reg,
                    tgt_length_reg,
                    padded_reg,
                ),
            ),
            span=span,
        )
        ctx.emit_encode_and_write(
            target_rr, fl, spliced_reg, offset_reg, extent=target_ref.extent, span=span
        )
    else:
        ctx.emit_encode_and_write(
            target_rr,
            fl,
            result_str_reg,
            offset_reg,
            extent=target_ref.extent,
            span=span,
        )


def _ref_mod_length(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    match operand.ref_mod_length:
        case None:
            return ctx.const_to_reg(999999, span=span)
        case length:
            return eval_ref_mod_expr(ctx, length, materialised, span=span)


def _ref_mod_number(
    ctx: EmitContext,
    decoded: Register,
    operand: RefModOperand,
    start: RefModExpr,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    start_0indexed = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            operator=BinopKind.SUB,
            left=eval_ref_mod_expr(ctx, start, materialised, span=span),
            right=ctx.const_to_reg(1, span=span),
            result_reg=start_0indexed,
        ),
        span=span,
    )
    sliced = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=sliced,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(
                ctx.emit_to_string(decoded, span=span),
                start_0indexed,
                _ref_mod_length(ctx, operand, materialised, span=span),
            ),
        ),
        span=span,
    )
    number = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=number,
            func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
            args=(sliced,),
        ),
        span=span,
    )
    return number


def _read_receiver(
    ctx: EmitContext,
    receiver: ArithmeticReceiver,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    decoded = ctx.emit_decode_field(
        receiver.region,
        receiver.ref.fl,
        receiver.ref.offset_reg,
        extent=receiver.ref.extent,
        span=span,
    )
    match receiver.operand.ref_mod_start:
        case None:
            return decoded
        case start:
            return _ref_mod_number(
                ctx, decoded, receiver.operand, start, materialised, span=span
            )


def _resolve_receiver(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> ArithmeticReceiver:
    ref, region = ctx.resolve_field_ref(
        operand.name,
        materialised,
        operand.qualifiers,
        subscripts=operand.subscripts,
        span=span,
    )
    return ArithmeticReceiver(operand=operand, ref=ref, region=region)


def _decode_operand(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> ArithmeticValue:
    if not ctx.has_field(operand.name, materialised):
        literal = ctx.parse_literal(translate_cobol_figurative(operand.name))
        return _operand_value(
            ctx, operand, ctx.const_to_reg(literal, span=span), materialised
        )
    receiver = _resolve_receiver(ctx, operand, materialised, span=span)
    return _operand_value(
        ctx,
        operand,
        _read_receiver(ctx, receiver, materialised, span=span),
        materialised,
    )


def _sum_operands(
    ctx: EmitContext,
    operands: Sequence[RefModOperand],
    receivers: Sequence[RefModOperand],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> ArithmeticValue:
    values = [_decode_operand(ctx, o, materialised, span=span) for o in operands]
    return reduce(
        lambda total, value: _emit_verb_operation(
            ctx, "ADD", total, value, receivers, materialised, span=span
        ),
        values[1:],
        values[0],
    )


def _write_result(
    ctx: EmitContext,
    receiver: ArithmeticReceiver,
    result: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    _emit_arithmetic_writeback(
        ctx,
        receiver.operand,
        receiver.ref,
        receiver.region,
        ctx.emit_to_string(result, span=span),
        materialised,
        span=span,
    )


def _stored_value(
    ctx: EmitContext,
    receiver: ArithmeticReceiver,
    result: Register,
    *,
    span: SourceSpan | None = None,
) -> Register:
    if not receiver.operand.rounded:
        return result
    rounded = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=rounded,
            func_name=FuncName(BuiltinName.COBOL_ROUND),
            args=(
                result,
                ctx.const_to_reg(
                    receiver_rounding_places(receiver.ref.fl.type_descriptor),
                    span=span,
                ),
            ),
        ),
        span=span,
    )
    return rounded


def _write_unless_size_error(
    ctx: EmitContext,
    receiver: ArithmeticReceiver,
    result: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    stored = _stored_value(ctx, receiver, result, span=span)
    overflow = _compute_overflow_flag(
        ctx, stored, receiver.ref.fl.type_descriptor, span=span
    )
    write_label = ctx.fresh_label("size_ok")
    skip_label = ctx.fresh_label("size_err_skip")
    ctx.emit_inst(
        BranchIf(cond_reg=overflow, branch_targets=(skip_label, write_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=write_label), span=span)
    _write_result(ctx, receiver, stored, materialised, span=span)
    ctx.emit_inst(Branch(label=skip_label), span=span)
    ctx.emit_inst(Label_(label=skip_label), span=span)
    return overflow


def _any_flag(
    ctx: EmitContext, flags: Sequence[Register], *, span: SourceSpan | None = None
) -> Register:
    def _or(left: Register, right: Register) -> Register:
        combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=combined,
                operator=resolve_binop("or"),
                left=left,
                right=right,
            ),
            span=span,
        )
        return combined

    return reduce(_or, flags[1:], flags[0])


def _emit_zero_divisor_guard(
    ctx: EmitContext,
    op: str,
    divisor: ArithmeticValue,
    on_size_err_label: CodeLabel,
    *,
    span: SourceSpan | None = None,
) -> None:
    if op != "DIVIDE":
        return
    is_zero = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=is_zero,
            operator=resolve_binop("=="),
            left=divisor.register,
            right=ctx.const_to_reg(0, span=span),
        ),
        span=span,
    )
    compute_label = ctx.fresh_label("divide_compute")
    ctx.emit_inst(
        BranchIf(cond_reg=is_zero, branch_targets=(on_size_err_label, compute_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=compute_label), span=span)


def _emit_size_error_arm(
    ctx: EmitContext,
    label: CodeLabel,
    body: Sequence[CobolStatementType],
    follow_up: Callable[[], None],
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    ctx.emit_inst(Label_(label=label), span=span)
    follow_up()
    for child in body:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)


ReceiverStep = Callable[[RefModOperand], tuple[ArithmeticReceiver, Register]]
SizeErrorGuard = Callable[[CodeLabel], None]
SizeErrorPhrases = ArithmeticStatement | ComputeStatement


def _store_guarded(
    ctx: EmitContext,
    stmt: SizeErrorPhrases,
    guard: SizeErrorGuard,
    receivers: Sequence[RefModOperand],
    step: ReceiverStep,
    follow_up: Callable[[], None],
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = stmt.span
    on_label = ctx.fresh_label("on_size_err")
    not_on_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")
    guard(on_label)
    flags = [
        _write_unless_size_error(ctx, *step(target), materialised, span=span)
        for target in receivers
    ]
    ctx.emit_inst(
        BranchIf(
            cond_reg=_any_flag(ctx, flags, span=span),
            branch_targets=(on_label, not_on_label),
        ),
        span=span,
    )
    _emit_size_error_arm(
        ctx,
        on_label,
        stmt.on_size_error,
        _no_follow_up,
        end_label,
        materialised,
        span=span,
    )
    _emit_size_error_arm(
        ctx,
        not_on_label,
        stmt.not_on_size_error,
        follow_up,
        end_label,
        materialised,
        span=span,
    )
    ctx.emit_inst(Label_(label=end_label), span=span)


def _store_unguarded(
    ctx: EmitContext,
    target: RefModOperand,
    step: ReceiverStep,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    receiver, result = step(target)
    _write_result(
        ctx,
        receiver,
        _stored_value(ctx, receiver, result, span=span),
        materialised,
        span=span,
    )


def _store(
    ctx: EmitContext,
    stmt: SizeErrorPhrases,
    guard: SizeErrorGuard,
    receivers: Sequence[RefModOperand],
    step: ReceiverStep,
    follow_up: Callable[[], None],
    materialised: MaterialisedSectionedLayout,
) -> None:
    if stmt.on_size_error or stmt.not_on_size_error:
        _store_guarded(ctx, stmt, guard, receivers, step, follow_up, materialised)
        return
    for target in receivers:
        _store_unguarded(ctx, target, step, materialised, span=stmt.span)
    follow_up()


def _no_size_error_guard(_on_label: CodeLabel) -> None:
    return None


def _no_follow_up() -> None:
    return None


def _in_place_step(
    ctx: EmitContext,
    op: str,
    sending: ArithmeticValue,
    materialised: MaterialisedSectionedLayout,
    span: SourceSpan | None,
    target: RefModOperand,
) -> tuple[ArithmeticReceiver, Register]:
    receiver = _resolve_receiver(ctx, target, materialised, span=span)
    current = _operand_value(
        ctx,
        target,
        _read_receiver(ctx, receiver, materialised, span=span),
        materialised,
    )
    return (
        receiver,
        _emit_verb_operation(
            ctx, op, current, sending, (target,), materialised, span=span
        ).register,
    )


def _giving_step(
    ctx: EmitContext,
    result: Register,
    materialised: MaterialisedSectionedLayout,
    span: SourceSpan | None,
    target: RefModOperand,
) -> tuple[ArithmeticReceiver, Register]:
    return _resolve_receiver(ctx, target, materialised, span=span), result


def _emit_remainder(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    dividend: ArithmeticValue,
    divisor: ArithmeticValue,
    quotient: ArithmeticValue,
    materialised: MaterialisedSectionedLayout,
) -> None:
    match stmt.remainder:
        case None:
            return
        case remainder_op:
            _write_remainder(
                ctx,
                remainder_op,
                dividend,
                divisor,
                quotient,
                materialised,
                span=stmt.span,
            )


def _write_remainder(
    ctx: EmitContext,
    remainder_op: RefModOperand,
    dividend: ArithmeticValue,
    divisor: ArithmeticValue,
    quotient: ArithmeticValue,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    truncated = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=truncated, func_name=FuncName("int"), args=(quotient.register,)
        ),
        span=span,
    )
    product = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=product,
            operator=resolve_binop("*"),
            left=truncated,
            right=divisor.register,
        ),
        span=span,
    )
    remainder = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=remainder,
            operator=resolve_binop("-"),
            left=dividend.register,
            right=product,
        ),
        span=span,
    )
    _write_result(
        ctx,
        _resolve_receiver(ctx, remainder_op, materialised, span=span),
        remainder,
        materialised,
        span=span,
    )


def _divisor_guard(
    ctx: EmitContext, stmt: ArithmeticStatement, divisor: ArithmeticValue
) -> SizeErrorGuard:
    return partial(_emit_zero_divisor_guard, ctx, stmt.op, divisor, span=stmt.span)


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE with every sending operand applied to every receiver."""
    if stmt.giving:
        _lower_arithmetic_giving(ctx, stmt, materialised)
        return
    sending = _sum_operands(
        ctx, stmt.operands, stmt.targets, materialised, span=stmt.span
    )
    step = partial(_in_place_step, ctx, stmt.op, sending, materialised, stmt.span)
    guard = _divisor_guard(ctx, stmt, sending)
    _store(ctx, stmt, guard, stmt.targets, step, _no_follow_up, materialised)


def _lower_arithmetic_giving(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = stmt.span
    first = _decode_operand(ctx, stmt.operands[0], materialised, span=span)
    rest = _sum_operands(ctx, stmt.operands[1:], stmt.giving, materialised, span=span)
    result = _emit_verb_operation(
        ctx, stmt.op, first, rest, stmt.giving, materialised, span=span
    )
    step = partial(_giving_step, ctx, result.register, materialised, span)
    remainder = partial(_emit_remainder, ctx, stmt, first, rest, result, materialised)
    guard = _divisor_guard(ctx, stmt, rest)
    _store(ctx, stmt, guard, stmt.giving, step, remainder, materialised)


def _compute_operand(target: ComputeTarget) -> RefModOperand:
    return RefModOperand(
        name=target.name,
        qualifiers=target.qualifiers,
        subscripts=target.subscripts,
        rounded=target.rounded,
    )


def _known_compute_target(
    ctx: EmitContext, target: ComputeTarget, materialised: MaterialisedSectionedLayout
) -> bool:
    if ctx.has_field(target.name, materialised):
        return True
    logger.warning("COMPUTE target %s not found in layout", target.name)
    return False


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    span = stmt.span
    targets = [
        _compute_operand(t)
        for t in stmt.targets
        if _known_compute_target(ctx, t, materialised)
    ]
    target_types = [
        (materialised.resolve(t.name, t.qualifiers)[0].type_descriptor, t.rounded)
        for t in targets
    ]
    result_reg = lower_expr_node(
        ctx,
        stmt.expression,
        materialised,
        receiver_decimals=max(
            (_receiver_decimals(td, rounded) for td, rounded in target_types), default=0
        ),
        floating_receiver=any(is_floating_type(td) for td, _ in target_types),
        span=span,
    )
    if not targets:
        return
    step = partial(_giving_step, ctx, result_reg, materialised, span)
    _store(ctx, stmt, _no_size_error_guard, targets, step, _no_follow_up, materialised)


def lower_if(
    ctx: EmitContext,
    stmt: IfStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """IF condition ... [ELSE ...] END-IF."""
    span = stmt.span
    cond_reg = ctx.lower_condition(stmt.condition, materialised, span=span)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    ctx.emit_inst(
        BranchIf(
            cond_reg=cond_reg,
            branch_targets=(true_label, false_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=true_label), span=span)
    for child in stmt.children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=false_label), span=span)
    for child in stmt.else_children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=end_label), span=span)


def _also_subject_ref(stmt, position: int, also_subject: str) -> dict:
    """The ALSO subject at ``position`` as a ref node.

    The structured one the bridge sent when the subject carries a slice, a
    subscript or a qualifier, and the bare name otherwise -- the same choice
    ``subject_ref`` makes for the first subject. ``also_subject_refs`` is
    positional and holds a slot for every ALSO subject, so a missing or empty
    entry means "this one is only a name" (red-dragon-ba1).
    """
    refs = stmt.also_subject_refs
    structured = refs[position] if position < len(refs) else {}
    return structured or {"kind": "ref", "name": also_subject}


def _when_operand_node(value: str) -> dict:
    """Classify an ``EVALUATE <subject> WHEN <value>`` value into a structured
    relation-operand dict, so it lowers through the same path the IF relation
    lowering uses (figuratives sized to the sibling, quoted literals intact).

    - figurative constant (SPACES / LOW-VALUES / ZEROS / ...) -> figurative node
    - quoted literal ('Y', ' ') -> lit node (quotes preserved)
    - anything else (a field name or bare number) -> ref node, which the operand
      lowering resolves as field-or-literal.
    """
    v = value.strip()
    if v.upper() in COBOL_FIGURATIVE_CONSTANTS:
        return {"kind": "figurative", "value": v.upper()}
    if len(v) >= 2 and v[0] in ("'", '"') and v[-1] == v[0]:
        return {"kind": "lit", "value": v}
    return {"kind": "ref", "name": v}


def lower_evaluate(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EVALUATE subject WHEN value ..."""
    end_label = ctx.fresh_label("eval_end")
    for child in stmt.children:
        _lower_evaluate_child(ctx, stmt, child, end_label, materialised)
    ctx.emit_inst(Label_(label=end_label), span=stmt.span)


def _lower_evaluate_child(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: CobolStatementType,
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    if isinstance(child, WhenStatement) and child.condition:
        _lower_when(ctx, stmt, child, end_label, materialised)
    elif isinstance(child, WhenOtherStatement):
        _lower_body(ctx, child.children, materialised)


def _lower_when(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """The WHEN's body when its condition holds, then out of the EVALUATE: only
    the first WHEN that matches runs."""
    span = stmt.span
    cond_reg = _when_condition(ctx, stmt, child, materialised)
    when_true = ctx.fresh_label("when_true")
    when_false = ctx.fresh_label("when_false")
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(when_true, when_false)),
        span=span,
    )
    ctx.emit_inst(Label_(label=when_true), span=span)
    _lower_body(ctx, child.children, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=when_false), span=span)


def _lower_body(
    ctx: EmitContext,
    statements: Sequence[CobolStatementType],
    materialised: MaterialisedSectionedLayout,
) -> None:
    for statement in statements:
        ctx.lower_statement(statement, materialised)


def _when_condition(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Whether a WHEN selects its body: its own condition, ORed with each stacked
    alternative's."""
    return reduce(
        lambda left, right: _or(ctx, stmt, left, right),
        (
            _when_alternative(ctx, stmt, alternative, materialised)
            for alternative in child.alternatives
        ),
        _when_alternative(ctx, stmt, child, materialised),
    )


def _or(
    ctx: EmitContext, stmt: EvaluateStatement, left: Register, right: Register
) -> Register:
    either = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(result_reg=either, operator=resolve_binop("or"), left=left, right=right),
        span=stmt.span,
    )
    return either


def _when_alternative(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """One condition of a WHEN -- with its THRU and its ALSO pairs -- against the
    EVALUATE's subjects."""
    span = stmt.span
    if isinstance(child.condition, str) and child.condition.strip().upper() == "ANY":
        # WHEN ANY on the primary subject is a wildcard that always
        # matches (mirrors the existing ANY handling for ALSO
        # conditions below) — red-dragon-9j01.
        cond_reg = ctx.const_to_reg(True, span=span)
    elif isinstance(child.condition, dict):
        cond_dict = child.condition
        if "kind" in cond_dict:
            # Expression-kind dict (e.g. lit, ref, binop) — the CICS prepass
            # has already resolved DFHRESP nodes to lit nodes before we get here.
            # Compare the evaluated value against the EVALUATE subject.
            if stmt.subject_ref is not None:
                # A sliced, subscripted or qualified subject is a
                # REFERENCE, not a name: compare it the way the IF
                # relation path compares one (red-dragon-sfih).
                cond_reg = ctx.lower_condition(
                    {
                        "relation": {
                            "left": stmt.subject_ref,
                            "op": "==",
                            "right": cond_dict,
                        }
                    },
                    materialised,
                    span=span,
                )
            elif stmt.subject and stmt.subject.upper() != "TRUE":
                val_reg = lower_expr_node(
                    ctx, expr_from_dict(cond_dict), materialised, span=span
                )
                if ctx.has_field(stmt.subject, materialised):
                    subject_ref, subject_rr = ctx.resolve_field_ref(
                        stmt.subject, materialised, span=span
                    )
                    subject_reg = ctx.emit_decode_field(
                        subject_rr,
                        subject_ref.fl,
                        subject_ref.offset_reg,
                        extent=subject_ref.extent,
                        span=span,
                    )
                else:
                    subject_reg = ctx.const_to_reg(
                        ctx.parse_literal(stmt.subject), span=span
                    )
                cond_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=cond_reg,
                        operator=resolve_binop("=="),
                        left=Register(str(subject_reg)),
                        right=Register(str(val_reg)),
                    ),
                    span=span,
                )
            else:
                cond_reg = lower_expr_node(
                    ctx, expr_from_dict(cond_dict), materialised, span=span
                )
        else:
            # Full conditional expression (EVALUATE TRUE WHEN ...): route through
            # the same structured lowering the IF path uses.
            cond_reg = ctx.lower_condition(cond_dict, materialised, span=span)
    elif stmt.subject and stmt.subject.upper() != "TRUE":
        # WHEN <value> against an EVALUATE subject: lower "subject = value"
        # through the SAME structured relation path the IF lowering uses,
        # rather than re-parsing a "subject = value" string. The string
        # path split on whitespace (destroying quoted spaces) and treated
        # figuratives (SPACES / LOW-VALUES) as the literal text, so
        # WHEN SPACES / WHEN ' ' never matched a blank field (red-dragon-z6ad).
        subj_node: dict = stmt.subject_ref or {
            "kind": "ref",
            "name": stmt.subject,
        }
        if child.condition_thru is not None:
            # WHEN <from> THRU <to>: emit (subject >= from) AND (subject <= to)
            ge_reg = ctx.lower_condition(
                {
                    "relation": {
                        "left": subj_node,
                        "op": ">=",
                        "right": _when_operand_node(child.condition),
                    }
                },
                materialised,
                span=span,
            )
            le_reg = ctx.lower_condition(
                {
                    "relation": {
                        "left": subj_node,
                        "op": "<=",
                        "right": _when_operand_node(child.condition_thru),
                    }
                },
                materialised,
                span=span,
            )
            cond_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=cond_reg,
                    operator=resolve_binop("&&"),
                    left=Register(str(ge_reg)),
                    right=Register(str(le_reg)),
                ),
                span=span,
            )
        else:
            relation = {
                "left": subj_node,
                "op": "==",
                "right": _when_operand_node(child.condition),
            }
            cond_reg = ctx.lower_condition(
                {"relation": relation}, materialised, span=span
            )
    else:
        # subject is TRUE with a flat string condition (e.g. a level-88
        # name): keep the text-condition path.
        cond_reg = _lower_condition_str(
            ctx, child.condition, materialised, ctx._condition_index, span=span
        )
    # AND in also-subject=also-condition pairs (EVALUATE A ALSO B WHEN x ALSO y)
    for position, (also_subj, also_cond) in enumerate(
        # strict=False: a WHEN with fewer ALSO values than the EVALUATE has
        # subjects is malformed, and truncating is what this has always done.
        zip(stmt.also_subjects, child.also_conditions, strict=False)
    ):
        if isinstance(also_cond, str) and also_cond.upper() == "ANY":
            continue
        # The ALSO subject is a subject: it takes the same structured ref
        # node the first one does, so a slice or a qualifier on it survives
        # instead of resolving the whole field (red-dragon-ba1).
        also_subj_ref = _also_subject_ref(stmt, position, also_subj)
        if isinstance(also_cond, dict) and "kind" in also_cond:
            also_val_reg = lower_expr_node(
                ctx, expr_from_dict(also_cond), materialised, span=span
            )
            if ctx.has_field(also_subj, materialised):
                also_ref, also_rr = ctx.resolve_field_ref(
                    also_subj, materialised, span=span
                )
                also_subj_reg = ctx.emit_decode_field(
                    also_rr,
                    also_ref.fl,
                    also_ref.offset_reg,
                    extent=also_ref.extent,
                    span=span,
                )
            else:
                also_subj_reg = ctx.const_to_reg(
                    ctx.parse_literal(also_subj), span=span
                )
            also_cond_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=also_cond_reg,
                    operator=resolve_binop("=="),
                    left=Register(str(also_subj_reg)),
                    right=Register(str(also_val_reg)),
                ),
                span=span,
            )
        elif (
            isinstance(also_cond, dict) and "from" in also_cond and "thru" in also_cond
        ):
            # WHEN ... ALSO <from> THRU <to>: emit range comparison
            also_subj_node: dict = also_subj_ref
            also_ge_reg = ctx.lower_condition(
                {
                    "relation": {
                        "left": also_subj_node,
                        "op": ">=",
                        "right": _when_operand_node(also_cond["from"]),
                    }
                },
                materialised,
                span=span,
            )
            also_le_reg = ctx.lower_condition(
                {
                    "relation": {
                        "left": also_subj_node,
                        "op": "<=",
                        "right": _when_operand_node(also_cond["thru"]),
                    }
                },
                materialised,
                span=span,
            )
            also_cond_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=also_cond_reg,
                    operator=resolve_binop("&&"),
                    left=Register(str(also_ge_reg)),
                    right=Register(str(also_le_reg)),
                ),
                span=span,
            )
        elif isinstance(also_cond, dict):
            also_cond_reg = ctx.lower_condition(also_cond, materialised, span=span)
        elif also_subj.upper() == "TRUE":
            # EVALUATE ... ALSO TRUE: the WHEN value is a CONDITION, the same
            # as it is under a first subject of TRUE. Comparing it against a
            # field named TRUE -- which no program declares -- made the pair
            # unmatchable (red-dragon-c7p).
            also_cond_reg = _lower_condition_str(
                ctx,
                also_cond,
                materialised,
                ctx._condition_index,
                span=span,
            )
        else:
            relation = {
                "left": also_subj_ref,
                "op": "==",
                "right": _when_operand_node(also_cond),
            }
            also_cond_reg = ctx.lower_condition(
                {"relation": relation}, materialised, span=span
            )
        and_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=and_reg,
                operator=resolve_binop("&&"),
                left=Register(str(cond_reg)),
                right=Register(str(also_cond_reg)),
            ),
            span=span,
        )
        cond_reg = and_reg
    return cond_reg


def lower_continue(
    ctx: EmitContext,
    stmt: ContinueStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CONTINUE — no-op, emit nothing."""
    pass


def lower_next_sentence(
    ctx: EmitContext,
    stmt: NextSentenceStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """NEXT SENTENCE — branch past the period ending the enclosing sentence."""
    ctx.emit_inst(Branch(label=ctx.sentence_exit()), span=stmt.span)


def lower_exit(
    ctx: EmitContext,
    stmt: ExitStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PARAGRAPH / SECTION / PERFORM [CYCLE] branch past what they leave.

    A plain EXIT is the paragraph-end no-op and emits nothing.
    """
    if stmt.kind not in _EXIT_TARGETS:
        return
    ctx.emit_inst(Branch(label=_EXIT_TARGETS[stmt.kind](ctx)), span=stmt.span)


_EXIT_TARGETS: Mapping[ExitKind, Callable[[EmitContext], CodeLabel]] = {
    ExitKind.PARAGRAPH: EmitContext.paragraph_exit,
    ExitKind.SECTION: EmitContext.section_exit,
    ExitKind.PERFORM: EmitContext.perform_leave,
    ExitKind.PERFORM_CYCLE: EmitContext.perform_cycle,
}


def _leaf_fields_of(target_fl: FieldLayout, layout: DataLayout) -> list[FieldLayout]:
    """Return leaf FieldLayouts contained within target_fl's byte range.

    A leaf is a field that has no other fields falling strictly inside its range.
    Returns [target_fl] if target_fl is itself a leaf (not a group item).
    """
    target_start = target_fl.offset
    target_end = target_fl.offset + target_fl.byte_length

    contained = [
        fl
        for fl in layout.all_leaves()
        if fl.name != target_fl.name
        and fl.offset >= target_start
        and fl.offset + fl.byte_length <= target_end
    ]

    if not contained:
        return [target_fl]

    return [fl for fl in contained if _is_leaf_among(fl, contained)]


def _is_leaf_among(fl: FieldLayout, contained: Sequence[FieldLayout]) -> bool:
    fl_end = fl.offset + fl.byte_length
    return not any(
        other.name != fl.name
        and other.offset >= fl.offset
        and other.offset + other.byte_length <= fl_end
        for other in contained
    )


def lower_initialize(
    ctx: EmitContext,
    stmt: InitializeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INITIALIZE field1 field2 — reset to type-appropriate defaults.

    For group items, each elementary (leaf) child is reset with the
    type-appropriate default: spaces for ALPHANUMERIC, zeros for numeric.
    """
    span = stmt.span
    for operand in stmt.operands:
        if not ctx.has_field(operand, materialised):
            logger.warning("INITIALIZE target %s not found in layout", operand)
            continue
        ref, _rr = ctx.resolve_field_ref(operand, materialised, span=span)
        # Look up the layout section that owns this field for _leaf_fields_of
        _fl_layout, _ = materialised.resolve(operand)
        # Determine which DataLayout to use for leaf enumeration
        # We use the working_storage layout as a fallback; the actual layout
        # is the one from the resolved section.
        # Since _leaf_fields_of needs the full DataLayout for all_leaves(),
        # we pick the right section layout.
        ws_layout, _ = materialised.working_storage
        ls_layout, _ = materialised.local_storage
        lk_layout, _ = materialised.linkage
        if ws_layout.exists(operand):
            section_layout = ws_layout
        elif ls_layout.exists(operand):
            section_layout = ls_layout
        else:
            section_layout = lk_layout
        for leaf_fl in _leaf_fields_of(ref.fl, section_layout):
            leaf_ref, leaf_rr = ctx.resolve_field_ref(
                leaf_fl.name, materialised, span=span
            )
            td = leaf_fl.type_descriptor
            if td.holds_characters:
                default = " " * td.total_digits
            else:
                default = "0"
            ctx.emit_field_encode(
                leaf_rr,
                leaf_fl,
                default,
                leaf_ref.offset_reg,
                extent=leaf_ref.extent,
                span=span,
            )


def _set_condition_name(
    ctx: EmitContext,
    condition_name: str,
    value_str: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """SET <88-condition-name> TO TRUE|FALSE — write the VALUE into the parent.

    For TRUE: write the first ConditionValue's literal into the parent elementary
    field (mirrors the condition-read path in condition_lowering). For FALSE: the
    ConditionNameIndex/ConditionValue carries no FALSE-value, so we warn and skip
    rather than guessing (never silently behave as TRUE).
    """
    truth = str(value_str).strip().upper()
    entry = ctx._condition_index.lookup(condition_name)

    if truth == "FALSE":
        if not entry.parent_field_name:
            logger.warning(
                "SET %s TO FALSE: condition not in index — skipping", condition_name
            )
            return
        parent_ref, parent_rr = ctx.resolve_field_ref(
            entry.parent_field_name, materialised, span=span
        )
        if parent_ref.fl.type_descriptor.holds_characters:
            # WHEN SET TO FALSE IS not in scope — write SPACES (field-length fill)
            false_val: object = " " * max(parent_ref.fl.byte_length, 1)
        else:
            false_val = 0
        ctx.emit_encode_and_write(
            parent_rr,
            parent_ref.fl,
            ctx.const_to_reg(false_val, span=span),
            parent_ref.offset_reg,
            extent=parent_ref.extent,
            span=span,
        )
        return

    if truth != "TRUE":
        logger.warning(
            "SET %s TO %r is not a TRUE/FALSE condition assignment — skipping",
            condition_name,
            value_str,
        )
        return

    if not entry.values:
        logger.warning(
            "SET %s TO TRUE has no condition VALUE to write — skipping",
            condition_name,
        )
        return

    # First discrete value / range-low is what makes the condition true.
    cv = entry.values[0]
    parent_ref, parent_rr = ctx.resolve_field_ref(
        entry.parent_field_name, materialised, span=span
    )

    # For an ALPHANUMERIC (PIC X) parent, the 88 VALUE is a character literal —
    # write its characters verbatim. It must reach the alphanumeric encoder as a
    # quoted string-literal Const so the VM keeps it a str; an unquoted digit
    # literal (VALUE '1', '0') is parsed as an int, which __string_to_bytes then
    # rejects as non-str and silently drops, leaving the byte unchanged
    # (red-dragon-0sq2). Numeric parents keep the parsed numeric literal.
    #
    # A figurative-constant VALUE (LOW-VALUES / SPACES / ZEROS / HIGH-VALUES) must
    # expand to its fill character repeated to the parent's byte length — NOT be
    # written as the literal text 'LOW-VALUES' (CardDemo COACTUPC
    # ACUP-DETAILS-NOT-FETCHED VALUES LOW-VALUES, SPACES).
    fig_fill = COBOL_FIGURATIVE_CONSTANTS.get(cv.from_val.upper())
    if parent_ref.fl.type_descriptor.holds_characters:
        if fig_fill is not None:
            filled = fig_fill * max(parent_ref.fl.byte_length, 1)
            value_reg = ctx.const_to_reg(filled, span=span)
        else:
            value_reg = ctx.const_to_reg(cv.from_val, span=span)
    elif fig_fill is not None and cv.from_val.upper() in ("ZERO", "ZEROS", "ZEROES"):
        value_reg = ctx.const_to_reg(0, span=span)
    else:
        value_reg = ctx.const_to_reg(ctx.parse_literal(cv.from_val), span=span)
    ctx.emit_encode_and_write(
        parent_rr,
        parent_ref.fl,
        value_reg,
        parent_ref.offset_reg,
        extent=parent_ref.extent,
        span=span,
    )


def lower_set(
    ctx: EmitContext,
    stmt: SetStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """SET target TO value / SET target UP|DOWN BY value.

    A target that names a level-88 condition (e.g. SET FLG-ON TO TRUE) writes the
    condition's VALUE into its parent elementary field, so a later test of that 88
    reads true. SET <88> TO FALSE requires a captured false-value; absent one it
    warns rather than guessing.
    """
    if is_pointer_set(ctx, stmt, materialised):
        lower_pointer_set(ctx, stmt, materialised)
        return
    span = stmt.span
    condition_index = ctx._condition_index
    if stmt.set_type == "TO":
        value_str = stmt.values[0].text if stmt.values else "0"
        for target_name in (target.text for target in stmt.targets):
            if condition_index.has_condition(target_name):
                _set_condition_name(
                    ctx, target_name, value_str, materialised, span=span
                )
                continue
            if not ctx.has_field(target_name, materialised):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(
                target_name, materialised, span=span
            )
            # SET A TO B is legal when B is a data item; stmt.values[0] is raw
            # operand text from the bridge and is never tested for being a name.
            # Untested, it wrote the two characters "B" — which encodes into a
            # numeric field as 0, so the symptom is a plausible zero, not a crash.
            if ctx.has_field(str(value_str), materialised):
                src_ref, src_rr = ctx.resolve_field_ref(
                    str(value_str), materialised, span=span
                )
                value_str_reg = ctx.emit_decode_field(
                    src_rr,
                    src_ref.fl,
                    src_ref.offset_reg,
                    extent=src_ref.extent,
                    span=span,
                )
            else:
                value_str_reg = ctx.const_to_reg(str(value_str), span=span)
            ctx.emit_encode_and_write(
                target_rr,
                target_ref.fl,
                value_str_reg,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )
    elif stmt.set_type == "BY":
        step_val = stmt.values[0].text if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target_name in (target.text for target in stmt.targets):
            if not ctx.has_field(target_name, materialised):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(
                target_name, materialised, span=span
            )
            tgt_decoded = ctx.emit_decode_field(
                target_rr,
                target_ref.fl,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )
            # SET ... UP/DOWN BY <data-item> takes the same path as TO above.
            if ctx.has_field(str(step_val), materialised):
                step_ref, step_rr = ctx.resolve_field_ref(
                    str(step_val), materialised, span=span
                )
                step_reg = ctx.emit_decode_field(
                    step_rr,
                    step_ref.fl,
                    step_ref.offset_reg,
                    extent=step_ref.extent,
                    span=span,
                )
            else:
                step_reg = ctx.const_to_reg(ctx.parse_literal(step_val), span=span)
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(op),
                    left=tgt_decoded,
                    right=step_reg,
                ),
                span=span,
            )
            result_str_reg = ctx.emit_to_string(result_reg, span=span)
            ctx.emit_encode_and_write(
                target_rr,
                target_ref.fl,
                result_str_reg,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )


def _lower_display_operand(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower one DISPLAY operand to a register holding its display string."""
    if ctx.has_field(operand.name, materialised):
        ref, rr = ctx.resolve_field_ref(
            operand.name, materialised, subscripts=operand.subscripts, span=span
        )
        display_reg = ctx.emit_decode_field_characters(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
    else:
        display_reg = ctx.const_to_reg(str(operand.name), span=span)

    if operand.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(
            ctx, operand.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0indexed_reg,
                operator=resolve_binop("-"),
                left=raw_start_reg,
                right=one_reg,
            ),
            span=span,
        )
        length_reg = (
            eval_ref_mod_expr(ctx, operand.ref_mod_length, materialised, span=span)
            if operand.ref_mod_length is not None
            else ctx.const_to_reg(9999, span=span)
        )
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(display_reg, start_0indexed_reg, length_reg),
            ),
            span=span,
        )
        display_reg = sliced_reg

    return display_reg


def lower_display(
    ctx: EmitContext,
    stmt: DisplayStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DISPLAY operand [operand ...] — concatenate every operand onto one line.

    COBOL concatenates the operands with no separator; we lower each to its
    display string, fold them with string-concat, and print the result ONCE.
    """
    span = stmt.span
    operand_regs = [
        _lower_display_operand(ctx, operand, materialised, span=span)
        for operand in stmt.operands
    ]
    if not operand_regs:
        return

    combined_reg = operand_regs[0]
    for next_reg in operand_regs[1:]:
        folded = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=folded,
                func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
                args=(combined_reg, next_reg),
            ),
            span=span,
        )
        combined_reg = folded

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print"),
            args=(combined_reg,),
        ),
        span=span,
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN — unconditionally terminates the entire run unit, unlike
    GOBACK/EXIT PROGRAM (which return control to the caller).

    Nothing is returned, so there is no caller to copy RETURN-CODE up to — but the
    run unit ends HERE, wherever "here" is, so this program's RETURN-CODE is the
    one the operating system receives, even when STOP RUN is issued inside a
    subprogram and the entry program never finishes (red-dragon-cvwu).
    """
    emit_publish_run_unit_return_code(
        ctx,
        emit_return_code_load(ctx, materialised, span=stmt.span),
        span=stmt.span,
    )
    ctx.emit_inst(Halt_(), span=stmt.span)


def lower_goback(
    ctx: EmitContext,
    stmt: GobackStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GOBACK — return control to the caller, carrying RETURN-CODE."""
    lower_program_exit(ctx, materialised, span=stmt.span)


def lower_exit_program(
    ctx: EmitContext,
    stmt: ExitProgramStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PROGRAM — return control to the caller, carrying RETURN-CODE."""
    lower_program_exit(ctx, materialised, span=stmt.span)


def _lower_computed_goto(
    ctx: EmitContext,
    computed: ComputedGoto,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """GO TO p1 ... pN DEPENDING ON idx — branch to the idx-th (1-based) target;
    out-of-range (idx <= 0 or idx > N) falls through to the next statement."""
    index = computed.index
    ref, rr = ctx.resolve_field_ref(
        index.name,
        materialised,
        index.qualifiers,
        subscripts=index.subscripts,
        span=span,
    )
    idx_reg = ctx.emit_decode_field(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )
    for k, target in enumerate(computed.targets, start=1):
        k_reg = ctx.const_to_reg(k, span=span)
        cmp_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=cmp_reg,
                operator=resolve_binop("=="),
                left=Register(str(idx_reg)),
                right=Register(str(k_reg)),
            ),
            span=span,
        )
        match_lbl = ctx.fresh_label("goto_dep_match")
        next_lbl = ctx.fresh_label("goto_dep_next")
        ctx.emit_inst(
            BranchIf(cond_reg=cmp_reg, branch_targets=(match_lbl, next_lbl)),
            span=span,
        )
        ctx.emit_inst(Label_(label=match_lbl), span=span)
        ctx.emit_inst(Branch(label=ctx.procedure_label(target)), span=span)
        ctx.emit_inst(Label_(label=next_lbl), span=span)


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO — simple, computed (DEPENDING ON), or altered."""
    span = stmt.span
    form = stmt.form
    if isinstance(form, SimpleGoto):
        ctx.emit_inst(Branch(label=ctx.procedure_label(form.target)), span=span)
    elif isinstance(form, ComputedGoto):
        _lower_computed_goto(ctx, form, materialised, span=span)
    # AlteredGoto: GO TO. with target supplied by ALTER — no-op, behavior
    # intentionally unchanged (not exercised by any test).
