"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.figurative_constants import (
    COBOL_FIGURATIVE_CONSTANTS,
    translate_cobol_figurative,
)
from interpreter.cobol.ref_mod import (
    RefModLiteral,
    RefModReference,
    RefModLengthOf,
    RefModBinOp,
    RefModExpr,
    RefModOperand,
    FunctionCallOperand,
)
from interpreter.cobol.cobol_statements import (
    ArithmeticStatement,
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
    StopRunStatement,
    WhenOtherStatement,
    WhenStatement,
)
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.condition_lowering import _lower_condition_str, lower_expr_node
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.operator_kind import resolve_binop, BinopKind
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    Label_,
    Return_,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register

logger = logging.getLogger(__name__)

ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}


def _compute_overflow_flag(
    ctx: EmitContext,
    result_reg: Register,
    td: CobolTypeDescriptor,
) -> Register:
    """Emit CONST/BINOP sequence to compute overflow bool register.

    Returns the register holding True iff result_reg overflows td's bounds.
    Does NOT emit a branch — caller decides what to branch on.
    """
    max_val = 10**td.total_digits - 1
    max_reg = ctx.const_to_reg(max_val)
    over_max = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=over_max,
            operator=resolve_binop(">"),
            left=result_reg,
            right=max_reg,
        )
    )
    if td.signed:
        min_reg = ctx.const_to_reg(-max_val)
        under_min = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=under_min,
                operator=resolve_binop("<"),
                left=result_reg,
                right=min_reg,
            )
        )
        overflow_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=overflow_reg,
                operator=resolve_binop("or"),
                left=over_max,
                right=under_min,
            )
        )
        return overflow_reg
    return over_max


def emit_overflow_check(
    ctx: EmitContext,
    result_reg: Register,
    td: CobolTypeDescriptor,
    on_size_err_label: CodeLabel,
    not_on_size_err_label: CodeLabel,
) -> None:
    """Emit overflow detection and BRANCH_IF to the supplied labels."""
    overflow_reg = _compute_overflow_flag(ctx, result_reg, td)
    ctx.emit_inst(
        BranchIf(
            cond_reg=overflow_reg,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )


def eval_ref_mod_expr(
    ctx: EmitContext,
    expr: RefModExpr,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Evaluate a reference modification expression to an IR register.

    Handles three cases:
    - RefModLiteral: numeric literal → Const → register
    - RefModReference: data item name → resolve field → decode → to_string → register
    - RefModBinOp: binary operation → evaluate left/right → emit Binop → register
    """
    if isinstance(expr, RefModLiteral):
        # Literal: numeric value for reference modification
        # Keep as unquoted numeric literal so arithmetic operations work
        value = expr.value
        return ctx.const_to_reg(value)

    elif isinstance(expr, RefModReference):
        # Field reference: resolve field → decode
        # Return the decoded numeric value (don't convert to string)
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, rr = ctx.resolve_field_ref(name, materialised)
            decoded_reg = ctx.emit_decode_field(rr, field_ref.fl, field_ref.offset_reg)
            logging.debug(
                f"eval_ref_mod_expr: RefModReference {name} → decoded_reg={decoded_reg}"
            )
            # Return the decoded numeric value directly
            return decoded_reg
        else:
            # Unknown field: treat as literal numeric 0
            logging.debug(f"eval_ref_mod_expr: RefModReference {name} (unknown) → 0")
            return ctx.const_to_reg("0")

    elif isinstance(expr, RefModLengthOf):
        # LENGTH OF <field>: the field's byte length (a compile-time constant),
        # NOT a decode of its value. Used in ref-mod start/length expressions
        # such as DEST(LENGTH OF G + 1 : LENGTH OF H) (red-dragon-oq2c).
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, _ = ctx.resolve_field_ref(name, materialised)
            return ctx.const_to_reg(field_ref.fl.byte_length)
        logging.warning("eval_ref_mod_expr: LENGTH OF unknown field %s → 0", name)
        return ctx.const_to_reg("0")

    elif isinstance(expr, RefModBinOp):
        # Binary operation: evaluate left and right, emit Binop
        left_reg = eval_ref_mod_expr(ctx, expr.left, materialised)
        right_reg = eval_ref_mod_expr(ctx, expr.right, materialised)
        result_reg = ctx.fresh_reg()

        op_str = expr.op
        binop_kind = resolve_binop(op_str)

        ctx.emit_inst(
            Binop(
                operator=binop_kind,
                left=left_reg,
                right=right_reg,
                result_reg=result_reg,
            )
        )
        return result_reg

    else:
        # Fallback: treat as literal zero
        return ctx.const_to_reg('"0"')


# Maps canonical COBOL intrinsic function names to COBOL-layer builtin names.
_INTRINSIC_FUNCTIONS = {
    "UPPER-CASE": BuiltinName.UPPER_CASE,
    "LOWER-CASE": BuiltinName.LOWER_CASE,
    "CURRENT-DATE": BuiltinName.CURRENT_DATE,
}


def _lower_function_arg_to_string(
    ctx: EmitContext,
    arg: dict,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower one intrinsic-function argument dict to a string-valued register.

    Field references are decoded then stringified (intrinsics like UPPER-CASE
    operate on character data); literals are parsed as constants.
    """
    kind = arg.get("kind", "lit")
    if kind == "ref":
        name = arg.get("name", "")
        if ctx.has_field(name, materialised):
            ref, rr = ctx.resolve_field_ref(name, materialised)
            decoded = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
            return ctx.emit_to_string(decoded)
        return ctx.const_to_reg(ctx.parse_literal(name))
    if kind == "lit":
        return ctx.const_to_reg(ctx.parse_literal(arg.get("value", "")))
    # Arithmetic / other expression args: lower via the expression path, then
    # stringify so the builtin (e.g. UPPER-CASE) receives character data.
    from interpreter.cobol.condition_lowering import _lower_expr_dict

    value_reg = _lower_expr_dict(ctx, arg, materialised)
    return ctx.emit_to_string(value_reg)


def lower_function_operand(
    ctx: EmitContext,
    operand: FunctionCallOperand,
    materialised: MaterialisedSectionedLayout,
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
            return _lower_function_arg_to_string(ctx, operand.args[0], materialised)
        return ctx.const_to_reg('""')

    arg_regs = tuple(
        _lower_function_arg_to_string(ctx, arg, materialised) for arg in operand.args
    )
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(builtin),
            args=arg_regs,
        )
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

    # Intrinsic FUNCTION source (e.g. FUNCTION UPPER-CASE(...)): evaluate to a
    # value register, then distribute to every receiving field. Functions carry
    # no source-side reference modification, so the ref-mod block is skipped.
    if isinstance(stmt.source, FunctionCallOperand):
        source_value_reg = lower_function_operand(ctx, stmt.source, materialised)
        for target in stmt.targets:
            _store_move_value(ctx, target, source_value_reg, materialised)
        return

    # Resolve the source field once (when it is a field). A numeric-DISPLAY
    # (zoned) source carries an extra character representation, picked per target
    # by category-pair in _store_move_value (red-dragon-0fqr).
    source_fl: FieldLayout | None = None
    # Get the source value (decode field or literal) — evaluated ONCE.
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(stmt.source.name, materialised)
        source_fl = source_ref.fl
        decoded_reg = ctx.emit_decode_field(
            source_rr, source_ref.fl, source_ref.offset_reg
        )
        value_str_reg = ctx.emit_to_string(decoded_reg)
    else:
        literal = translate_cobol_figurative(stmt.source.name)
        # Ensure unquoted literals (e.g. digit-only "12345") are stored as
        # quoted strings so _parse_const returns str, not int/float.
        if not (
            len(literal) >= 2 and literal[0] in ('"', "'") and literal[-1] == literal[0]
        ):
            literal = f'"{literal}"'
        value_str_reg = ctx.const_to_reg(literal)

    # Handle reference modification if present
    logging.debug(
        f"lower_move: {stmt.source.name} ref_mod_start={stmt.source.ref_mod_start}, ref_mod_length={stmt.source.ref_mod_length}"
    )
    if stmt.source.ref_mod_start is not None:
        logging.debug(
            f"lower_move: Detected reference modification on {stmt.source.name}: "
            f"start={stmt.source.ref_mod_start}, length={stmt.source.ref_mod_length}"
        )
        # Evaluate start and length expressions
        start_reg = eval_ref_mod_expr(ctx, stmt.source.ref_mod_start, materialised)
        # COBOL uses 1-indexed positions, but SLICE uses 0-indexed.
        # Convert: start_0indexed = start_1indexed - 1
        one_reg = ctx.const_to_reg("1")  # Numeric 1, not string "1"
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=start_reg,
                right=one_reg,
                result_reg=start_0indexed_reg,
            )
        )

        if stmt.source.ref_mod_length is not None:
            # Both start and length specified: SLICE operation
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised
            )
            result_reg = ctx.fresh_reg()
            logging.debug(
                f"lower_move: Emitting SLICE with value_reg={value_str_reg}, "
                f"start_reg={start_0indexed_reg}, length_reg={length_reg}, result_reg={result_reg}"
            )
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, length_reg),
                )
            )
            value_str_reg = result_reg
        else:
            # Only start specified, no length: SLICE from start to end
            # Use the length of the value string minus start position
            # For now, use a very large number as length to get substring to end
            large_length = ctx.const_to_reg('"999999"')
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, large_length),
                )
            )
            value_str_reg = result_reg

    # For a numeric-DISPLAY (zoned) source with NO source reference modification,
    # compute its zoned character representation ONCE (width-preserving digit
    # characters). _store_move_value uses this only for alphanumeric receivers,
    # where COBOL moves the sending field's characters left-justified rather than
    # the numeric value (red-dragon-0fqr). Ref-modified sources keep the existing
    # sliced-string path.
    zoned_display_reg: Register | None = None
    if (
        source_fl is not None
        and stmt.source.ref_mod_start is None
        and source_fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL
    ):
        zoned_display_reg = ctx.emit_decode_zoned_display(
            source_rr, source_fl, source_ref.offset_reg
        )

    # Store the (once-evaluated) source value into each receiving field. Each
    # target gets its own reference modification and PICTURE conversion; the
    # base source value (source_value_reg) is never clobbered across targets.
    source_value_reg = value_str_reg
    for target in stmt.targets:
        _store_move_value(
            ctx, target, source_value_reg, materialised, zoned_display_reg
        )


def _store_move_value(
    ctx: EmitContext,
    target: RefModOperand,
    source_value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    zoned_display_reg: Register | None = None,
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
    target_ref, target_rr = ctx.resolve_field_ref(target.name, materialised)

    if (
        zoned_display_reg is not None
        and target.ref_mod_start is None
        and target_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC
    ):
        source_value_reg = zoned_display_reg

    target_value_reg = source_value_reg

    # Handle target reference modification (write path): MOVE X TO Y(start:length)
    if target.ref_mod_start is not None:
        logging.debug(
            f"lower_move: Detected reference modification on target {target.name}: "
            f"start={target.ref_mod_start}, length={target.ref_mod_length}"
        )
        # Load current target field value as string (needed for SPLICE)
        target_decoded = ctx.emit_decode_field(
            target_rr, target_ref.fl, target_ref.offset_reg
        )
        target_str_reg = ctx.emit_to_string(target_decoded)

        # Evaluate target ref mod start; convert 1-indexed → 0-indexed
        tgt_start_reg = eval_ref_mod_expr(ctx, target.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg("1")
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_start_reg,
                right=one_reg,
                result_reg=tgt_start_0indexed_reg,
            )
        )

        # Evaluate target ref mod length (or use large sentinel for "to end")
        if target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(ctx, target.ref_mod_length, materialised)
        else:
            tgt_length_reg = ctx.const_to_reg("999999")

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
            )
        )
        target_value_reg = spliced_reg

    ctx.emit_encode_and_write(
        target_rr, target_ref.fl, target_value_reg, target_ref.offset_reg
    )


def lower_move_corresponding(
    ctx: EmitContext,
    stmt: MoveCorrespondingStatement,
    layout: DataLayout,
    region_reg: Register,
) -> None:
    """MOVE CORRESPONDING src TO dst — copy matching direct leaf fields."""
    src_layout = layout.lookup_group(stmt.source)

    for target_name in stmt.targets:
        dst_layout = layout.lookup_group(target_name)
        matching = src_layout.fields.keys() & dst_layout.fields.keys()

        for name in matching:
            src_fl = src_layout.fields[name]
            dst_fl = dst_layout.fields[name]

            src_ref = ctx.resolve_field_ref_from(src_fl, region_reg)
            decoded = ctx.emit_decode_field(region_reg, src_fl, src_ref.offset_reg)
            value_str = ctx.emit_to_string(decoded)

            dst_ref = ctx.resolve_field_ref_from(dst_fl, region_reg)
            ctx.emit_encode_and_write(region_reg, dst_fl, value_str, dst_ref.offset_reg)


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
    if stmt.giving:
        lower_arithmetic_giving(ctx, stmt, materialised)
        return

    target_ref, target_rr = ctx.resolve_field_ref(stmt.target, materialised)

    # Decode source operand
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(stmt.source.name, materialised)
        src_decoded = ctx.emit_decode_field(
            source_rr, source_ref.fl, source_ref.offset_reg
        )

        # Handle reference modification on source
        if stmt.source.ref_mod_start is not None:
            # Convert to string first
            src_str_reg = ctx.emit_to_string(src_decoded)

            # Evaluate start and length
            start_reg = eval_ref_mod_expr(ctx, stmt.source.ref_mod_start, materialised)
            # Convert 1-indexed to 0-indexed
            one_reg = ctx.const_to_reg("1")
            start_0indexed_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    operator=BinopKind.SUB,
                    left=start_reg,
                    right=one_reg,
                    result_reg=start_0indexed_reg,
                )
            )

            # Perform slice
            if stmt.source.ref_mod_length is not None:
                length_reg = eval_ref_mod_expr(
                    ctx, stmt.source.ref_mod_length, materialised
                )
            else:
                length_reg = ctx.const_to_reg("999999")

            sliced_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=sliced_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(src_str_reg, start_0indexed_reg, length_reg),
                )
            )

            # Convert back to float for arithmetic
            src_decoded = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=src_decoded,
                    func_name=FuncName("float"),
                    args=(sliced_reg,),
                )
            )
    else:
        src_decoded = ctx.const_to_reg(float(stmt.source.name))

    tgt_decoded = ctx.emit_decode_field(target_rr, target_ref.fl, target_ref.offset_reg)

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        op = ARITHMETIC_OPS[stmt.op]
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(op),
                left=tgt_decoded,
                right=src_decoded,
            )
        )
        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
        )
        return

    # ON SIZE ERROR / NOT ON SIZE ERROR path
    on_size_err_label = ctx.fresh_label("on_size_err")
    not_on_size_err_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")

    # DIVIDE only: pre-Binop division-by-zero guard
    if stmt.op == "DIVIDE":
        zero_reg = ctx.const_to_reg(0)
        divzero_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=divzero_reg,
                operator=resolve_binop("=="),
                left=src_decoded,
                right=zero_reg,
            )
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=divzero_reg,
                branch_targets=(on_size_err_label, compute_label),
            )
        )
        ctx.emit_inst(Label_(label=compute_label))

    op = ARITHMETIC_OPS[stmt.op]
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(op),
            left=tgt_decoded,
            right=src_decoded,
        )
    )

    emit_overflow_check(
        ctx,
        result_reg,
        target_ref.fl.type_descriptor,
        on_size_err_label,
        not_on_size_err_label,
    )

    ctx.emit_inst(Label_(label=on_size_err_label))
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    result_str_reg = ctx.emit_to_string(result_reg)
    ctx.emit_encode_and_write(
        target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
    )
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_arithmetic_giving(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MULTIPLY/DIVIDE X BY/INTO Y GIVING Z."""

    def _decode_operand(operand: RefModOperand) -> Register:
        field_name = operand.name
        if ctx.has_field(field_name, materialised):
            ref, rr = ctx.resolve_field_ref(field_name, materialised)
            decoded = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)

            # Apply ref_mod if present
            if operand.ref_mod_start is not None:
                src_str = ctx.emit_to_string(decoded)
                start_reg = eval_ref_mod_expr(ctx, operand.ref_mod_start, materialised)
                # Convert 1-indexed to 0-indexed
                one_reg = ctx.const_to_reg(1)
                zero_indexed_start = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=zero_indexed_start,
                        operator=resolve_binop("-"),
                        left=start_reg,
                        right=one_reg,
                    )
                )

                length_reg = (
                    eval_ref_mod_expr(ctx, operand.ref_mod_length, materialised)
                    if operand.ref_mod_length is not None
                    else ctx.const_to_reg(999999)
                )

                # Emit STRING_SLICE
                sliced = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=sliced,
                        func_name=FuncName("STRING_SLICE"),
                        args=(src_str, zero_indexed_start, length_reg),
                    )
                )

                # Convert result back to float
                result = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=result,
                        func_name=FuncName("float"),
                        args=(sliced,),
                    )
                )
                return result

            return decoded
        return ctx.const_to_reg(float(field_name))

    def _decode_field(name: str) -> Register:
        """Decode a plain string field name (for target operand)."""
        if ctx.has_field(name, materialised):
            ref, rr = ctx.resolve_field_ref(name, materialised)
            return ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(float(name))

    left_reg = _decode_operand(stmt.source)
    right_reg = _decode_field(stmt.target)

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if has_clause and stmt.op == "DIVIDE":
        on_size_err_label = ctx.fresh_label("on_size_err")
        not_on_size_err_label = ctx.fresh_label("not_on_size_err")
        end_label = ctx.fresh_label("size_err_end")
        zero_reg = ctx.const_to_reg(0)
        divzero_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=divzero_reg,
                operator=resolve_binop("=="),
                left=right_reg,
                right=zero_reg,
            )
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=divzero_reg,
                branch_targets=(on_size_err_label, compute_label),
            )
        )
        ctx.emit_inst(Label_(label=compute_label))
    elif has_clause:
        on_size_err_label = ctx.fresh_label("on_size_err")
        not_on_size_err_label = ctx.fresh_label("not_on_size_err")
        end_label = ctx.fresh_label("size_err_end")

    op = ARITHMETIC_OPS[stmt.op]
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(op),
            left=left_reg,
            right=right_reg,
        )
    )

    if not has_clause:
        for giving_name in stmt.giving:
            giving_ref, giving_rr = ctx.resolve_field_ref(giving_name, materialised)
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                giving_rr, giving_ref.fl, result_str_reg, giving_ref.offset_reg
            )
        return

    # Compute combined overflow flag across all GIVING fields
    giving_pairs = [ctx.resolve_field_ref(n, materialised) for n in stmt.giving]
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
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
            )
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=combined_flag,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )

    ctx.emit_inst(Label_(label=on_size_err_label))
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    for ref, rr in giving_pairs:
        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(rr, ref.fl, result_str_reg, ref.offset_reg)
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    result_reg = lower_expr_node(ctx, stmt.expression, materialised)

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        result_str_reg = ctx.emit_to_string(result_reg)
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, materialised):
                logger.warning("COMPUTE target %s not found in layout", target_name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(target_name, materialised)
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
            )
        return

    on_size_err_label = ctx.fresh_label("on_size_err")
    not_on_size_err_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")

    # Resolve all valid targets up front
    target_pairs: list[tuple] = []
    for target_name in stmt.targets:
        if not ctx.has_field(target_name, materialised):
            logger.warning("COMPUTE target %s not found in layout", target_name)
            continue
        target_pairs.append(ctx.resolve_field_ref(target_name, materialised))

    # Guard: no valid targets means no writes and no overflow check — execute
    # not_on_size_error path (same as fast path: silent skip).
    if not target_pairs:
        return

    # OR overflow flags across all targets (all-or-nothing semantics)
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
        for ref, _ in target_pairs
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
            )
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=combined_flag,
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )

    ctx.emit_inst(Label_(label=on_size_err_label))
    for child in stmt.on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    result_str_reg = ctx.emit_to_string(result_reg)
    for ref, rr in target_pairs:
        ctx.emit_encode_and_write(rr, ref.fl, result_str_reg, ref.offset_reg)
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_if(
    ctx: EmitContext,
    stmt: IfStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """IF condition ... [ELSE ...] END-IF."""
    cond_reg = ctx.lower_condition(stmt.condition, materialised)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    ctx.emit_inst(
        BranchIf(
            cond_reg=cond_reg,
            branch_targets=(true_label, false_label),
        )
    )

    ctx.emit_inst(Label_(label=true_label))
    for child in stmt.children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    for child in stmt.else_children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_evaluate(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EVALUATE subject WHEN value ..."""
    end_label = ctx.fresh_label("eval_end")

    for child in stmt.children:
        if isinstance(child, WhenStatement) and child.condition:
            if isinstance(child.condition, dict):
                # Full conditional expression (EVALUATE TRUE WHEN ...): route through
                # the same structured lowering the IF path uses.
                cond_reg = ctx.lower_condition(child.condition, materialised)
            else:
                # WHEN <value> against an EVALUATE subject — build "subject = value".
                if stmt.subject and stmt.subject.upper() != "TRUE":
                    full_condition = f"{stmt.subject} = {child.condition}"
                else:
                    full_condition = child.condition
                cond_reg = _lower_condition_str(
                    ctx, full_condition, materialised, ctx._condition_index
                )
            when_true = ctx.fresh_label("when_true")
            when_false = ctx.fresh_label("when_false")
            ctx.emit_inst(
                BranchIf(
                    cond_reg=cond_reg,
                    branch_targets=(when_true, when_false),
                )
            )
            ctx.emit_inst(Label_(label=when_true))
            for grandchild in child.children:
                ctx.lower_statement(grandchild, materialised)
            ctx.emit_inst(Branch(label=end_label))
            ctx.emit_inst(Label_(label=when_false))
        elif isinstance(child, WhenOtherStatement):
            for grandchild in child.children:
                ctx.lower_statement(grandchild, materialised)

    ctx.emit_inst(Label_(label=end_label))


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
    for operand in stmt.operands:
        if not ctx.has_field(operand, materialised):
            logger.warning("INITIALIZE target %s not found in layout", operand)
            continue
        ref, rr = ctx.resolve_field_ref(operand, materialised)
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
        if ws_layout.lookup_as_storage(operand) is not None:
            section_layout = ws_layout
        elif ls_layout.lookup_as_storage(operand) is not None:
            section_layout = ls_layout
        else:
            section_layout = lk_layout
        for leaf_fl in _leaf_fields_of(ref.fl, section_layout):
            leaf_ref, leaf_rr = ctx.resolve_field_ref(leaf_fl.name, materialised)
            td = leaf_fl.type_descriptor
            if td.category == CobolDataCategory.ALPHANUMERIC:
                default = " " * td.total_digits
            else:
                default = "0"
            ctx.emit_field_encode(leaf_rr, leaf_fl, default, leaf_ref.offset_reg)


def _set_condition_name(
    ctx: EmitContext,
    condition_name: str,
    value_str: str,
    materialised: MaterialisedSectionedLayout,
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
        logger.warning(
            "SET %s TO FALSE unsupported (no FALSE value captured) — skipping",
            condition_name,
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
    parent_ref, parent_rr = ctx.resolve_field_ref(entry.parent_field_name, materialised)

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
    if parent_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC:
        if fig_fill is not None:
            filled = fig_fill * max(parent_ref.fl.byte_length, 1)
            value_reg = ctx.const_to_reg('"' + filled + '"')
        else:
            value_reg = ctx.const_to_reg(f'"{cv.from_val}"')
    elif fig_fill is not None and cv.from_val.upper() in ("ZERO", "ZEROS", "ZEROES"):
        value_reg = ctx.const_to_reg(0)
    else:
        value_reg = ctx.const_to_reg(ctx.parse_literal(cv.from_val))
    ctx.emit_encode_and_write(
        parent_rr, parent_ref.fl, value_reg, parent_ref.offset_reg
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
    condition_index = ctx._condition_index
    if stmt.set_type == "TO":
        value_str = stmt.values[0] if stmt.values else "0"
        for target_name in stmt.targets:
            if condition_index.has_condition(target_name):
                _set_condition_name(ctx, target_name, value_str, materialised)
                continue
            if not ctx.has_field(target_name, materialised):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(target_name, materialised)
            value_str_reg = ctx.const_to_reg(str(value_str))
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, value_str_reg, target_ref.offset_reg
            )
    elif stmt.set_type == "BY":
        step_val = stmt.values[0] if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, materialised):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(target_name, materialised)
            tgt_decoded = ctx.emit_decode_field(
                target_rr, target_ref.fl, target_ref.offset_reg
            )
            step_reg = ctx.const_to_reg(ctx.parse_literal(step_val))
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(op),
                    left=tgt_decoded,
                    right=step_reg,
                )
            )
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
            )


def lower_display(
    ctx: EmitContext,
    stmt: DisplayStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DISPLAY field-or-literal."""
    operand = stmt.operand

    if ctx.has_field(operand.name, materialised):
        ref, rr = ctx.resolve_field_ref(operand.name, materialised)
        decoded_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        display_reg = ctx.emit_to_string(decoded_reg)
    else:
        display_reg = ctx.const_to_reg(str(operand.name))

    if operand.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(ctx, operand.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg(1)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0indexed_reg,
                operator=resolve_binop("-"),
                left=raw_start_reg,
                right=one_reg,
            )
        )
        length_reg = (
            eval_ref_mod_expr(ctx, operand.ref_mod_length, materialised)
            if operand.ref_mod_length is not None
            else ctx.const_to_reg(9999)
        )
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(display_reg, start_0indexed_reg, length_reg),
            )
        )
        display_reg = sliced_reg

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print"),
            args=(display_reg,),
        )
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value=0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_goback(
    ctx: EmitContext,
    stmt: GobackStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GOBACK — return control to the caller (same as STOP RUN at the IR level)."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value=0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_exit_program(
    ctx: EmitContext,
    stmt: ExitProgramStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PROGRAM — return control to the caller."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value=0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO paragraph-name."""
    ctx.emit_inst(Branch(label=CodeLabel(f"para_{stmt.target}")))
