"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging

from cobol_asg.cobol_expression import expr_from_dict
from cobol_asg.cobol_statements import (
    ArithmeticCorrespondingStatement,
    ArithmeticStatement,
    ComputedGoto,
    ComputeStatement,
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
    SetStatement,
    SimpleGoto,
    StopRunStatement,
    WhenOtherStatement,
    WhenStatement,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
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
from interpreter.cobol.arithmetic_scale import field_scale, is_floating_type
from interpreter.cobol.arithmetic_scale import receiver_decimals as _receiver_decimals
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_lowering import (
    _float_operand,
    _lower_condition_str,
    lower_expr_node,
)
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.figurative_constants import (
    COBOL_FIGURATIVE_CONSTANTS,
    raw_figurative_byte,
    translate_cobol_figurative,
)
from interpreter.cobol.lower_program_exit import (
    emit_publish_run_unit_return_code,
    emit_return_code_load,
    lower_program_exit,
)
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    Halt_,
    Label_,
    Return_,
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
    ctx: EmitContext, name: str, materialised: MaterialisedSectionedLayout
):
    if not ctx.has_field(name, materialised):
        return None
    return materialised.resolve(name)[0].type_descriptor


def _operand_scale(
    ctx: EmitContext, name: str, materialised: MaterialisedSectionedLayout
) -> Scale:
    td = _operand_type(ctx, name, materialised)
    if td is not None:
        return field_scale(td)
    try:
        from_literal(translate_cobol_figurative(name))
    except ValueError:
        return Scale(1, 0)
    return literal_scale(translate_cobol_figurative(name))


def _emit_verb_operation(
    ctx: EmitContext,
    op: str,
    left_reg: Register,
    right_reg: Register,
    left_operand: RefModOperand,
    right_operand: RefModOperand,
    receivers: list[RefModOperand],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Emit ``left <op> right`` for an arithmetic verb, exact unless IBM's
    floating-point rule applies (a COMP-1/COMP-2 operand or receiver)."""
    result_reg = ctx.fresh_reg()
    types = [
        _operand_type(ctx, operand.name, materialised)
        for operand in (left_operand, right_operand, *receivers)
    ]
    if any(td is not None and is_floating_type(td) for td in types):
        # Convert BOTH operands first, exactly as the expression path does.
        # One side is a COMP-1/COMP-2 float while the other may be an exact
        # fixed-point value, and Python raises TypeError for Decimal + float:
        # the VM turns that into UNCOMPUTABLE and the receiver silently
        # stores zeros (e.g. ADD 0.5 TO WS-COMP2).
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(ARITHMETIC_OPS[op]),
                left=_float_operand(ctx, left_reg, True, span=span),
                right=_float_operand(ctx, right_reg, True, span=span),
            ),
            span=span,
        )
        return result_reg
    left_scale = _operand_scale(ctx, left_operand.name, materialised)
    right_scale = _operand_scale(ctx, right_operand.name, materialised)
    receiver_places = max(
        (
            _receiver_decimals(td, receiver.rounded)
            for receiver, td in zip(receivers, types[2:])
            if td is not None
        ),
        default=0,
    )
    operand_places = (
        left_scale.decimal_places
        if op == "DIVIDE"
        else max(left_scale.decimal_places, right_scale.decimal_places)
    )
    dmax = max(receiver_places, operand_places)
    if op in ("ADD", "SUBTRACT"):
        combined = add_scale(left_scale, right_scale)
    elif op == "MULTIPLY":
        combined = mul_scale(left_scale, right_scale)
    else:
        combined = div_scale(left_scale, right_scale, dmax)
    decimals_reg = ctx.const_to_reg(carry(combined, dmax).decimal_places, span=span)
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(_EXACT_VERB_BUILTINS[op]),
            args=(left_reg, right_reg, decimals_reg),
        ),
        span=span,
    )
    return result_reg


def _compute_overflow_flag(
    ctx: EmitContext,
    result_reg: Register,
    td: CobolTypeDescriptor,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Emit CONST/BINOP sequence to compute overflow bool register.

    Returns the register holding True iff result_reg overflows td's bounds.
    Does NOT emit a branch — caller decides what to branch on.
    """
    # result_reg holds the unscaled value (e.g. 999.99, not 99999), so the
    # overflow threshold must be sized by integer-digit capacity only —
    # td.total_digits includes decimal positions and would otherwise be off
    # by a factor of 10**decimal_digits (red-dragon-oiec).
    integer_digits = td.total_digits - td.decimal_digits
    max_val = 10**integer_digits - 1
    max_reg = ctx.const_to_reg(max_val, span=span)
    over_max = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=over_max,
            operator=resolve_binop(">"),
            left=result_reg,
            right=max_reg,
        ),
        span=span,
    )
    if td.signed:
        min_reg = ctx.const_to_reg(-max_val, span=span)
        under_min = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=under_min,
                operator=resolve_binop("<"),
                left=result_reg,
                right=min_reg,
            ),
            span=span,
        )
        overflow_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=overflow_reg,
                operator=resolve_binop("or"),
                left=over_max,
                right=under_min,
            ),
            span=span,
        )
        return overflow_reg
    return over_max


def emit_overflow_check(
    ctx: EmitContext,
    result_reg: Register,
    td: CobolTypeDescriptor,
    on_size_err_label: CodeLabel,
    not_on_size_err_label: CodeLabel,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Emit overflow detection and BRANCH_IF to the supplied labels."""
    overflow_reg = _compute_overflow_flag(ctx, result_reg, td, span=span)
    ctx.emit_inst(
        BranchIf(
            cond_reg=overflow_reg,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        ),
        span=span,
    )


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
    "RANDOM": BuiltinName.RANDOM,
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
    """
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
    # 0xFF / 0x00 in every receiver position — and must bypass the ASCII→EBCDIC
    # alphanumeric encoder, which would corrupt \xff into 0x6F (red-dragon-raxa).
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
    layout: DataLayout,
    region_reg: Register,
    region: RegionId,
) -> None:
    """MOVE CORRESPONDING src TO dst — copy matching direct leaf fields.

    ``region`` names the section buffer ``layout``/``region_reg`` belong to;
    it cannot be derived here because the FieldLayouts are taken straight out
    of ``layout`` rather than resolved by name.
    """
    span = stmt.span
    src_layout = layout.lookup_group(stmt.source)

    for target_name in stmt.targets:
        dst_layout = layout.lookup_group(target_name)
        matching = src_layout.fields.keys() & dst_layout.fields.keys()

        for name in matching:
            src_fl = src_layout.fields[name]
            dst_fl = dst_layout.fields[name]

            src_ref = ctx.resolve_field_ref_from(src_fl, region_reg, region, span=span)
            decoded = ctx.emit_decode_field(
                region_reg, src_fl, src_ref.offset_reg, extent=src_ref.extent, span=span
            )
            value_str = ctx.emit_to_string(decoded, span=span)

            dst_ref = ctx.resolve_field_ref_from(dst_fl, region_reg, region, span=span)
            ctx.emit_encode_and_write(
                region_reg,
                dst_fl,
                value_str,
                dst_ref.offset_reg,
                extent=dst_ref.extent,
                span=span,
            )


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
            return grp, reg, region
        except KeyError:
            pass
    return None


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

        src_ref = ctx.resolve_field_ref_from(src_fl, src_rr, src_region, span=span)
        src_val = ctx.emit_decode_field(
            src_rr, src_fl, src_ref.offset_reg, extent=src_ref.extent, span=span
        )

        dst_ref = ctx.resolve_field_ref_from(dst_fl, dst_rr, dst_region, span=span)
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
        if target_op.rounded:
            dec_digits_reg = ctx.const_to_reg(
                fl.type_descriptor.decimal_digits, span=span
            )
            rounded_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=rounded_reg,
                    func_name=FuncName(BuiltinName.COBOL_ROUND),
                    args=(result_str_reg, dec_digits_reg),
                ),
                span=span,
            )
            result_str_reg = rounded_reg
        ctx.emit_encode_and_write(
            target_rr,
            fl,
            result_str_reg,
            offset_reg,
            extent=target_ref.extent,
            span=span,
        )


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
    span = stmt.span
    if stmt.giving:
        lower_arithmetic_giving(ctx, stmt, materialised)
        return

    target_ref, target_rr = ctx.resolve_field_ref(
        stmt.target.name,
        materialised,
        stmt.target.qualifiers,
        subscripts=stmt.target.subscripts,
        span=span,
    )

    # Decode source operand
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(
            stmt.source.name, materialised, subscripts=stmt.source.subscripts, span=span
        )
        src_decoded = ctx.emit_decode_field(
            source_rr,
            source_ref.fl,
            source_ref.offset_reg,
            extent=source_ref.extent,
            span=span,
        )

        # Handle reference modification on source
        if stmt.source.ref_mod_start is not None:
            # Convert to string first
            src_str_reg = ctx.emit_to_string(src_decoded, span=span)

            # Evaluate start and length
            start_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_start, materialised, span=span
            )
            # Convert 1-indexed to 0-indexed
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

            # Perform slice
            if stmt.source.ref_mod_length is not None:
                length_reg = eval_ref_mod_expr(
                    ctx, stmt.source.ref_mod_length, materialised, span=span
                )
            else:
                length_reg = ctx.const_to_reg(999999, span=span)

            sliced_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=sliced_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(src_str_reg, start_0indexed_reg, length_reg),
                ),
                span=span,
            )

            # Parse the text as an exact number for arithmetic
            src_decoded = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=src_decoded,
                    func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
                    args=(sliced_reg,),
                ),
                span=span,
            )
    else:
        src_decoded = ctx.const_to_reg(
            ctx.parse_literal(translate_cobol_figurative(stmt.source.name)), span=span
        )

    tgt_decoded = ctx.emit_decode_field(
        target_rr,
        target_ref.fl,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )

    # Apply target ref-mod on the READ side: ADD 5 TO Y(4:3) should add to
    # the Y(4:3) substring value, not to the entire Y field.
    if stmt.target.ref_mod_start is not None:
        tgt_str = ctx.emit_to_string(tgt_decoded, span=span)
        tgt_rm_start = eval_ref_mod_expr(
            ctx, stmt.target.ref_mod_start, materialised, span=span
        )
        one_reg2 = ctx.const_to_reg(1, span=span)
        tgt_rm_start_0idx = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_rm_start,
                right=one_reg2,
                result_reg=tgt_rm_start_0idx,
            ),
            span=span,
        )
        tgt_rm_len = (
            eval_ref_mod_expr(ctx, stmt.target.ref_mod_length, materialised, span=span)
            if stmt.target.ref_mod_length is not None
            else ctx.const_to_reg(999999, span=span)
        )
        tgt_sliced = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=tgt_sliced,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(tgt_str, tgt_rm_start_0idx, tgt_rm_len),
            ),
            span=span,
        )
        tgt_decoded_as_num = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=tgt_decoded_as_num,
                func_name=FuncName("int"),
                args=(tgt_sliced,),
            ),
            span=span,
        )
        tgt_decoded = tgt_decoded_as_num

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        result_reg = _emit_verb_operation(
            ctx,
            stmt.op,
            tgt_decoded,
            src_decoded,
            stmt.target,
            stmt.source,
            [stmt.target],
            materialised,
            span=span,
        )
        result_str_reg = ctx.emit_to_string(result_reg, span=span)
        _emit_arithmetic_writeback(
            ctx,
            stmt.target,
            target_ref,
            target_rr,
            result_str_reg,
            materialised,
            span=span,
        )
        return

    # ON SIZE ERROR / NOT ON SIZE ERROR path
    on_size_err_label = ctx.fresh_label("on_size_err")
    not_on_size_err_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")

    # DIVIDE only: pre-Binop division-by-zero guard
    if stmt.op == "DIVIDE":
        zero_reg = ctx.const_to_reg(0, span=span)
        divzero_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=divzero_reg,
                operator=resolve_binop("=="),
                left=src_decoded,
                right=zero_reg,
            ),
            span=span,
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=divzero_reg,
                branch_targets=(on_size_err_label, compute_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=compute_label), span=span)

    result_reg = _emit_verb_operation(
        ctx,
        stmt.op,
        tgt_decoded,
        src_decoded,
        stmt.target,
        stmt.source,
        [stmt.target],
        materialised,
        span=span,
    )

    emit_overflow_check(
        ctx,
        result_reg,
        target_ref.fl.type_descriptor,
        on_size_err_label,
        not_on_size_err_label,
        span=span,
    )

    ctx.emit_inst(Label_(label=on_size_err_label), span=span)
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=not_on_size_err_label), span=span)
    result_str_reg = ctx.emit_to_string(result_reg, span=span)
    _emit_arithmetic_writeback(
        ctx, stmt.target, target_ref, target_rr, result_str_reg, materialised, span=span
    )
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=end_label), span=span)


def lower_arithmetic_giving(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MULTIPLY/DIVIDE X BY/INTO Y GIVING Z."""
    span = stmt.span

    def _decode_operand(operand: RefModOperand) -> Register:
        field_name = operand.name
        if ctx.has_field(field_name, materialised):
            ref, rr = ctx.resolve_field_ref(
                field_name, materialised, subscripts=operand.subscripts, span=span
            )
            decoded = ctx.emit_decode_field(
                rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            )

            # Apply ref_mod if present
            if operand.ref_mod_start is not None:
                src_str = ctx.emit_to_string(decoded, span=span)
                start_reg = eval_ref_mod_expr(
                    ctx, operand.ref_mod_start, materialised, span=span
                )
                # Convert 1-indexed to 0-indexed
                one_reg = ctx.const_to_reg(1, span=span)
                zero_indexed_start = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=zero_indexed_start,
                        operator=resolve_binop("-"),
                        left=start_reg,
                        right=one_reg,
                    ),
                    span=span,
                )

                length_reg = (
                    eval_ref_mod_expr(
                        ctx, operand.ref_mod_length, materialised, span=span
                    )
                    if operand.ref_mod_length is not None
                    else ctx.const_to_reg(999999, span=span)
                )

                # Emit STRING_SLICE
                sliced = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=sliced,
                        func_name=FuncName("STRING_SLICE"),
                        args=(src_str, zero_indexed_start, length_reg),
                    ),
                    span=span,
                )

                # Parse the sliced text as an exact number
                result = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=result,
                        func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
                        args=(sliced,),
                    ),
                    span=span,
                )
                return result

            return decoded
        return ctx.const_to_reg(
            ctx.parse_literal(translate_cobol_figurative(field_name)), span=span
        )

    left_reg = _decode_operand(stmt.source)
    right_reg = _decode_operand(stmt.target)

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if has_clause and stmt.op == "DIVIDE":
        on_size_err_label = ctx.fresh_label("on_size_err")
        not_on_size_err_label = ctx.fresh_label("not_on_size_err")
        end_label = ctx.fresh_label("size_err_end")
        zero_reg = ctx.const_to_reg(0, span=span)
        divzero_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=divzero_reg,
                operator=resolve_binop("=="),
                left=right_reg,
                right=zero_reg,
            ),
            span=span,
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=divzero_reg,
                branch_targets=(on_size_err_label, compute_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=compute_label), span=span)
    elif has_clause:
        on_size_err_label = ctx.fresh_label("on_size_err")
        not_on_size_err_label = ctx.fresh_label("not_on_size_err")
        end_label = ctx.fresh_label("size_err_end")

    result_reg = _emit_verb_operation(
        ctx,
        stmt.op,
        left_reg,
        right_reg,
        stmt.source,
        stmt.target,
        list(stmt.giving),
        materialised,
        span=span,
    )

    def _emit_remainder_writeback() -> None:
        # DIVIDE ... GIVING ... REMAINDER r: r = dividend - trunc(quotient) * divisor,
        # using the SAME left_reg/right_reg the quotient (result_reg) was computed
        # from, so REMAINDER stays consistent with whatever value GIVING writes
        # (red-dragon-w0wp).
        if stmt.op != "DIVIDE" or stmt.remainder is None:
            return
        trunc_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=trunc_reg, func_name=FuncName("int"), args=(result_reg,)
            ),
            span=span,
        )
        product_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=product_reg,
                operator=resolve_binop("*"),
                left=trunc_reg,
                right=right_reg,
            ),
            span=span,
        )
        remainder_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=remainder_reg,
                operator=resolve_binop("-"),
                left=left_reg,
                right=product_reg,
            ),
            span=span,
        )
        remainder_op = stmt.remainder
        remainder_ref, remainder_rr = ctx.resolve_field_ref(
            remainder_op.name,
            materialised,
            remainder_op.qualifiers,
            subscripts=remainder_op.subscripts,
            span=span,
        )
        remainder_str_reg = ctx.emit_to_string(remainder_reg, span=span)
        _emit_arithmetic_writeback(
            ctx,
            remainder_op,
            remainder_ref,
            remainder_rr,
            remainder_str_reg,
            materialised,
            span=span,
        )

    if not has_clause:
        for giving_op in stmt.giving:
            giving_ref, giving_rr = ctx.resolve_field_ref(
                giving_op.name,
                materialised,
                giving_op.qualifiers,
                subscripts=giving_op.subscripts,
                span=span,
            )
            result_str_reg = ctx.emit_to_string(result_reg, span=span)
            _emit_arithmetic_writeback(
                ctx,
                giving_op,
                giving_ref,
                giving_rr,
                result_str_reg,
                materialised,
                span=span,
            )
        _emit_remainder_writeback()
        return

    # Compute combined overflow flag across all GIVING fields.
    # Keep the giving_op alongside (ref, rr) so ref-mod write-back has it.
    giving_triples = [
        (
            g,
            *ctx.resolve_field_ref(
                g.name, materialised, g.qualifiers, subscripts=g.subscripts, span=span
            ),
        )
        for g in stmt.giving
    ]
    giving_pairs = [(ref, rr) for (_, ref, rr) in giving_triples]
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor, span=span)
        for ref, _ in giving_pairs
    ]
    combined_flag = overflow_flags[0]
    for flag in overflow_flags[1:]:
        new_combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_combined,
                operator=resolve_binop("or"),
                left=combined_flag,
                right=flag,
            ),
            span=span,
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=combined_flag,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=on_size_err_label), span=span)
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=not_on_size_err_label), span=span)
    for g_op, ref, rr in giving_triples:
        result_str_reg = ctx.emit_to_string(result_reg, span=span)
        _emit_arithmetic_writeback(
            ctx, g_op, ref, rr, result_str_reg, materialised, span=span
        )
    _emit_remainder_writeback()
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=end_label), span=span)


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    span = stmt.span
    # IBM ARITH(COMPAT): receivers (+1 for ROUNDED) size the division fraction.
    # This supersedes the unconditional force_division_float of red-dragon-vaxz:
    # a fraction mid-expression now survives because dmax takes it from the
    # receiver (1 / (1 + R) ** N into PIC 9V9(8) carries 8 decimal places),
    # while integer-only expressions still truncate (red-dragon-apoq).
    target_types = [
        (materialised.resolve(t.name)[0].type_descriptor, t.rounded)
        for t in stmt.targets
        if ctx.has_field(t.name, materialised)
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

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        result_str_reg = ctx.emit_to_string(result_reg, span=span)
        for target in stmt.targets:
            if not ctx.has_field(target.name, materialised):
                logger.warning("COMPUTE target %s not found in layout", target.name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(
                target.name, materialised, subscripts=target.subscripts, span=span
            )
            write_reg = result_str_reg
            if target.rounded:
                dec_digits_reg = ctx.const_to_reg(
                    target_ref.fl.type_descriptor.decimal_digits, span=span
                )
                rounded_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=rounded_reg,
                        func_name=FuncName(BuiltinName.COBOL_ROUND),
                        args=(write_reg, dec_digits_reg),
                    ),
                    span=span,
                )
                write_reg = rounded_reg
            ctx.emit_encode_and_write(
                target_rr,
                target_ref.fl,
                write_reg,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )
        return

    on_size_err_label = ctx.fresh_label("on_size_err")
    not_on_size_err_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")

    # Resolve all valid targets up front
    target_triples: list[tuple] = []
    for target in stmt.targets:
        if not ctx.has_field(target.name, materialised):
            logger.warning("COMPUTE target %s not found in layout", target.name)
            continue
        ref, rr = ctx.resolve_field_ref(
            target.name, materialised, subscripts=target.subscripts, span=span
        )
        target_triples.append((ref, rr, target))

    # Guard: no valid targets means no writes and no overflow check — execute
    # not_on_size_error path (same as fast path: silent skip).
    if not target_triples:
        return

    # OR overflow flags across all targets (all-or-nothing semantics)
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor, span=span)
        for ref, rr, _ in target_triples
    ]
    combined_flag = overflow_flags[0]
    for flag in overflow_flags[1:]:
        new_combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_combined,
                operator=resolve_binop("or"),
                left=combined_flag,
                right=flag,
            ),
            span=span,
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=combined_flag,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=on_size_err_label), span=span)
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=not_on_size_err_label), span=span)
    result_str_reg = ctx.emit_to_string(result_reg, span=span)
    for ref, rr, target in target_triples:
        write_reg = result_str_reg
        if target.rounded:
            dec_digits_reg = ctx.const_to_reg(
                ref.fl.type_descriptor.decimal_digits, span=span
            )
            rounded_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=rounded_reg,
                    func_name=FuncName(BuiltinName.COBOL_ROUND),
                    args=(write_reg, dec_digits_reg),
                ),
                span=span,
            )
            write_reg = rounded_reg
        ctx.emit_encode_and_write(
            rr, ref.fl, write_reg, ref.offset_reg, extent=ref.extent, span=span
        )
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=end_label), span=span)


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
    span = stmt.span
    end_label = ctx.fresh_label("eval_end")

    for child in stmt.children:
        if isinstance(child, WhenStatement) and child.condition:
            if (
                isinstance(child.condition, str)
                and child.condition.strip().upper() == "ANY"
            ):
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
                    isinstance(also_cond, dict)
                    and "from" in also_cond
                    and "thru" in also_cond
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
                    also_cond_reg = ctx.lower_condition(
                        also_cond, materialised, span=span
                    )
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
            when_true = ctx.fresh_label("when_true")
            when_false = ctx.fresh_label("when_false")
            ctx.emit_inst(
                BranchIf(
                    cond_reg=cond_reg,
                    branch_targets=(when_true, when_false),
                ),
                span=span,
            )
            ctx.emit_inst(Label_(label=when_true), span=span)
            for grandchild in child.children:
                ctx.lower_statement(grandchild, materialised)
            ctx.emit_inst(Branch(label=end_label), span=span)
            ctx.emit_inst(Label_(label=when_false), span=span)
        elif isinstance(child, WhenOtherStatement):
            for grandchild in child.children:
                ctx.lower_statement(grandchild, materialised)

    ctx.emit_inst(Label_(label=end_label), span=span)


def lower_continue(
    ctx: EmitContext,
    stmt: ContinueStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CONTINUE — no-op, emit nothing."""
    pass


def lower_exit(
    ctx: EmitContext,
    stmt: ExitStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT — no-op sentinel, emit nothing."""
    pass


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

    leaves = []
    for fl in contained:
        fl_start = fl.offset
        fl_end = fl.offset + fl.byte_length
        is_leaf = not any(
            other.name != fl.name
            and other.offset >= fl_start
            and other.offset + other.byte_length <= fl_end
            for other in contained
        )
        if is_leaf:
            leaves.append(fl)

    return leaves


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
        ref, rr = ctx.resolve_field_ref(operand, materialised, span=span)
        # Look up the layout section that owns this field for _leaf_fields_of
        fl_layout, _ = materialised.resolve(operand)
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
    span = stmt.span
    condition_index = ctx._condition_index
    if stmt.set_type == "TO":
        value_str = stmt.values[0] if stmt.values else "0"
        for target_name in stmt.targets:
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
        step_val = stmt.values[0] if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target_name in stmt.targets:
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
        ctx.emit_inst(Branch(label=CodeLabel(f"para_{target.paragraph}")), span=span)
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
        ctx.emit_inst(
            Branch(label=CodeLabel(f"para_{form.target.paragraph}")), span=span
        )
    elif isinstance(form, ComputedGoto):
        _lower_computed_goto(ctx, form, materialised, span=span)
    # AlteredGoto: GO TO. with target supplied by ALTER — no-op, behavior
    # intentionally unchanged (not exercised by any test).
