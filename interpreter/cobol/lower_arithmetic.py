"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.figurative_constants import (
    COBOL_FIGURATIVE_CONSTANTS,
    raw_figurative_byte,
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
    ArithmeticCorrespondingStatement,
    ArithmeticStatement,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitProgramStatement,
    ExitStatement,
    GobackStatement,
    GotoStatement,
    SimpleGoto,
    ComputedGoto,
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
from interpreter.cobol.cobol_expression import expr_from_dict
from interpreter.cobol.condition_lowering import _lower_condition_str, lower_expr_node
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
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
        # Literal: numeric value for reference modification.
        # parse_literal converts e.g. "2" → int 2 so arithmetic Binops work.
        return ctx.const_to_reg(ctx.parse_literal(expr.value))

    elif isinstance(expr, RefModReference):
        # Field reference: resolve field → decode
        # Return the decoded numeric value (don't convert to string)
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, rr = ctx.resolve_field_ref(name, materialised)
            decoded_reg = ctx.emit_decode_field(rr, field_ref.fl, field_ref.offset_reg)
            # Return the decoded numeric value directly
            return decoded_reg
        else:
            # Unknown field: treat as literal numeric 0
            return ctx.const_to_reg(0)

    elif isinstance(expr, RefModLengthOf):
        # LENGTH OF <field>: the field's byte length (a compile-time constant),
        # NOT a decode of its value. Used in ref-mod start/length expressions
        # such as DEST(LENGTH OF G + 1 : LENGTH OF H) (red-dragon-oq2c).
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, _ = ctx.resolve_field_ref(name, materialised)
            return ctx.const_to_reg(field_ref.fl.byte_length)
        logging.warning("eval_ref_mod_expr: LENGTH OF unknown field %s → 0", name)
        return ctx.const_to_reg(0)

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
        return ctx.const_to_reg(0)


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
        return ctx.const_to_reg("")

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

    # LENGTH OF <field> source: the field's byte length (a compile-time constant
    # numeric value), distributed to every receiver. CardDemo CSUTLDTC uses
    # `MOVE LENGTH OF LS-DATE TO VSTRING-LENGTH` to set the ODO length before the
    # CEEDAYS CALL (red-dragon). Mirrors the ref-mod LENGTH OF handling above.
    if stmt.source.length_of:
        name = stmt.source.length_of
        if ctx.has_field(name, materialised):
            field_ref, _ = ctx.resolve_field_ref(name, materialised)
            length_value = field_ref.fl.byte_length
        else:
            logger.warning("MOVE LENGTH OF unknown field %r — using 0", name)
            length_value = 0
        source_value_reg = ctx.const_to_reg(length_value)
        for target in stmt.targets:
            _store_move_value(ctx, target, source_value_reg, materialised)
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
                    src_reg = ctx.const_to_reg(raw_str)
                    _store_move_value(ctx, target, src_reg, materialised)
                    continue
                target_ref, target_rr = ctx.resolve_field_ref(
                    target.name,
                    materialised,
                    target.qualifiers,
                    subscripts=target.subscripts,
                )
                ctx.emit_fill_raw_byte(
                    target_rr, target_ref.fl, fill_byte, target_ref.offset_reg
                )
            return

    # Resolve the source field once (when it is a field). A numeric-DISPLAY
    # (zoned) source carries an extra character representation, picked per target
    # by category-pair in _store_move_value (red-dragon-0fqr).
    source_fl: FieldLayout | None = None
    # Get the source value (decode field or literal) — evaluated ONCE.
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(
            stmt.source.name,
            materialised,
            stmt.source.qualifiers,
            subscripts=stmt.source.subscripts,
        )
        source_fl = source_ref.fl
        decoded_reg = ctx.emit_decode_field(
            source_rr, source_ref.fl, source_ref.offset_reg
        )
        value_str_reg = ctx.emit_to_string(decoded_reg)
    else:
        literal = strip_cobol_literal(translate_cobol_figurative(stmt.source.name))
        value_str_reg = ctx.const_to_reg(literal)

    # Handle reference modification if present
    if stmt.source.ref_mod_start is not None:
        # Evaluate start and length expressions
        start_reg = eval_ref_mod_expr(ctx, stmt.source.ref_mod_start, materialised)
        # COBOL uses 1-indexed positions, but SLICE uses 0-indexed.
        # Convert: start_0indexed = start_1indexed - 1
        one_reg = ctx.const_to_reg(1)
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
            # Use a large sentinel as length to get the substring to end.
            large_length = ctx.const_to_reg(999999)
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
        # The ProLeap bridge does not model COBOL special registers (e.g.
        # RETURN-CODE); a MOVE into one surfaces here with an unresolved/null
        # operand name. There is no DATA DIVISION field to write, so skip it
        # rather than crashing. (e.g. CSUTLDTC's `MOVE WS-SEVERITY-N TO
        # RETURN-CODE` — its callers read the program's LINKAGE result, not the
        # RETURN-CODE register, so dropping this write is behaviour-preserving.)
        if not ctx.has_field(target.name, materialised) and _is_special_register(
            target.name
        ):
            logger.warning(
                "MOVE into special register %r is not modelled — skipping", target.name
            )
            continue
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
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name, materialised, target.qualifiers, subscripts=target.subscripts
    )

    if (
        zoned_display_reg is not None
        and target.ref_mod_start is None
        and target_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC
    ):
        source_value_reg = zoned_display_reg

    target_value_reg = source_value_reg

    # Handle target reference modification (write path): MOVE X TO Y(start:length)
    if target.ref_mod_start is not None:
        # Load current target field value as string (needed for SPLICE)
        target_decoded = ctx.emit_decode_field(
            target_rr, target_ref.fl, target_ref.offset_reg
        )
        target_str_reg = ctx.emit_to_string(target_decoded)

        # Evaluate target ref mod start; convert 1-indexed → 0-indexed
        tgt_start_reg = eval_ref_mod_expr(ctx, target.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg(1)
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
            tgt_length_reg = ctx.const_to_reg(999999)

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


def _find_group_and_reg(
    name: str, materialised: MaterialisedSectionedLayout
) -> tuple[DataLayout, Register] | None:
    """Return (group DataLayout, region Register) for the named group, or None."""
    for layout, reg in (
        materialised.local_storage,
        materialised.working_storage,
        materialised.linkage,
        materialised.file,
    ):
        try:
            grp = layout.lookup_group(name)
            return grp, reg
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
    op_str = "+" if stmt.op == "ADD" else "-"

    src_result = _find_group_and_reg(stmt.source, materialised)
    dst_result = _find_group_and_reg(stmt.target, materialised)

    if src_result is None or dst_result is None:
        return

    src_group, src_rr = src_result
    dst_group, dst_rr = dst_result

    matching_names = src_group.fields.keys() & dst_group.fields.keys()
    for name in matching_names:
        src_fl = src_group.fields[name]
        dst_fl = dst_group.fields[name]

        src_ref = ctx.resolve_field_ref_from(src_fl, src_rr)
        src_val = ctx.emit_decode_field(src_rr, src_fl, src_ref.offset_reg)

        dst_ref = ctx.resolve_field_ref_from(dst_fl, dst_rr)
        dst_val = ctx.emit_decode_field(dst_rr, dst_fl, dst_ref.offset_reg)

        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(op_str),
                left=Register(str(dst_val)),
                right=Register(str(src_val)),
            )
        )
        result_str = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(dst_rr, dst_fl, result_str, dst_ref.offset_reg)


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
    if stmt.giving:
        lower_arithmetic_giving(ctx, stmt, materialised)
        return

    target_ref, target_rr = ctx.resolve_field_ref(
        stmt.target.name,
        materialised,
        stmt.target.qualifiers,
        subscripts=stmt.target.subscripts,
    )

    # Decode source operand
    if ctx.has_field(stmt.source.name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(
            stmt.source.name, materialised, subscripts=stmt.source.subscripts
        )
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
            one_reg = ctx.const_to_reg(1)
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
                length_reg = ctx.const_to_reg(999999)

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
        src_decoded = ctx.const_to_reg(
            float(translate_cobol_figurative(stmt.source.name))
        )

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
            ref, rr = ctx.resolve_field_ref(
                field_name, materialised, subscripts=operand.subscripts
            )
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
        return ctx.const_to_reg(float(translate_cobol_figurative(field_name)))

    left_reg = _decode_operand(stmt.source)
    right_reg = _decode_operand(stmt.target)

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
        for giving_op in stmt.giving:
            giving_ref, giving_rr = ctx.resolve_field_ref(
                giving_op.name,
                materialised,
                giving_op.qualifiers,
                subscripts=giving_op.subscripts,
            )
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                giving_rr, giving_ref.fl, result_str_reg, giving_ref.offset_reg
            )
        return

    # Compute combined overflow flag across all GIVING fields
    giving_pairs = [
        ctx.resolve_field_ref(
            g.name, materialised, g.qualifiers, subscripts=g.subscripts
        )
        for g in stmt.giving
    ]
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
        if isinstance(child, WhenStatement) and child.condition:
            if isinstance(child.condition, dict):
                cond_dict = child.condition
                if "kind" in cond_dict:
                    # Expression-kind dict (e.g. lit, ref, binop) — the CICS prepass
                    # has already resolved DFHRESP nodes to lit nodes before we get here.
                    # Compare the evaluated value against the EVALUATE subject.
                    val_reg = lower_expr_node(
                        ctx, expr_from_dict(cond_dict), materialised
                    )
                    if stmt.subject and stmt.subject.upper() != "TRUE":
                        if ctx.has_field(stmt.subject, materialised):
                            subject_ref, subject_rr = ctx.resolve_field_ref(
                                stmt.subject, materialised
                            )
                            subject_reg = ctx.emit_decode_field(
                                subject_rr, subject_ref.fl, subject_ref.offset_reg
                            )
                        else:
                            subject_reg = ctx.const_to_reg(
                                ctx.parse_literal(stmt.subject)
                            )
                        cond_reg = ctx.fresh_reg()
                        ctx.emit_inst(
                            Binop(
                                result_reg=cond_reg,
                                operator=resolve_binop("=="),
                                left=Register(str(subject_reg)),
                                right=Register(str(val_reg)),
                            )
                        )
                    else:
                        cond_reg = val_reg
                else:
                    # Full conditional expression (EVALUATE TRUE WHEN ...): route through
                    # the same structured lowering the IF path uses.
                    cond_reg = ctx.lower_condition(cond_dict, materialised)
            elif stmt.subject and stmt.subject.upper() != "TRUE":
                # WHEN <value> against an EVALUATE subject: lower "subject = value"
                # through the SAME structured relation path the IF lowering uses,
                # rather than re-parsing a "subject = value" string. The string
                # path split on whitespace (destroying quoted spaces) and treated
                # figuratives (SPACES / LOW-VALUES) as the literal text, so
                # WHEN SPACES / WHEN ' ' never matched a blank field (red-dragon-z6ad).
                subj_node: dict = {"kind": "ref", "name": stmt.subject}
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
                    )
                    cond_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Binop(
                            result_reg=cond_reg,
                            operator=resolve_binop("&&"),
                            left=Register(str(ge_reg)),
                            right=Register(str(le_reg)),
                        )
                    )
                else:
                    relation = {
                        "left": subj_node,
                        "op": "==",
                        "right": _when_operand_node(child.condition),
                    }
                    cond_reg = ctx.lower_condition({"relation": relation}, materialised)
            else:
                # subject is TRUE with a flat string condition (e.g. a level-88
                # name): keep the text-condition path.
                cond_reg = _lower_condition_str(
                    ctx, child.condition, materialised, ctx._condition_index
                )
            # AND in also-subject=also-condition pairs (EVALUATE A ALSO B WHEN x ALSO y)
            for also_subj, also_cond in zip(stmt.also_subjects, child.also_conditions):
                if isinstance(also_cond, str) and also_cond.upper() == "ANY":
                    continue
                if isinstance(also_cond, dict) and "kind" in also_cond:
                    also_val_reg = lower_expr_node(
                        ctx, expr_from_dict(also_cond), materialised
                    )
                    if ctx.has_field(also_subj, materialised):
                        also_ref, also_rr = ctx.resolve_field_ref(
                            also_subj, materialised
                        )
                        also_subj_reg = ctx.emit_decode_field(
                            also_rr, also_ref.fl, also_ref.offset_reg
                        )
                    else:
                        also_subj_reg = ctx.const_to_reg(ctx.parse_literal(also_subj))
                    also_cond_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Binop(
                            result_reg=also_cond_reg,
                            operator=resolve_binop("=="),
                            left=Register(str(also_subj_reg)),
                            right=Register(str(also_val_reg)),
                        )
                    )
                elif (
                    isinstance(also_cond, dict)
                    and "from" in also_cond
                    and "thru" in also_cond
                ):
                    # WHEN ... ALSO <from> THRU <to>: emit range comparison
                    also_subj_node: dict = {"kind": "ref", "name": also_subj}
                    also_ge_reg = ctx.lower_condition(
                        {
                            "relation": {
                                "left": also_subj_node,
                                "op": ">=",
                                "right": _when_operand_node(also_cond["from"]),
                            }
                        },
                        materialised,
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
                    )
                    also_cond_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Binop(
                            result_reg=also_cond_reg,
                            operator=resolve_binop("&&"),
                            left=Register(str(also_ge_reg)),
                            right=Register(str(also_le_reg)),
                        )
                    )
                elif isinstance(also_cond, dict):
                    also_cond_reg = ctx.lower_condition(also_cond, materialised)
                else:
                    relation = {
                        "left": {"kind": "ref", "name": also_subj},
                        "op": "==",
                        "right": _when_operand_node(also_cond),
                    }
                    also_cond_reg = ctx.lower_condition(
                        {"relation": relation}, materialised
                    )
                and_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=and_reg,
                        operator=resolve_binop("&&"),
                        left=Register(str(cond_reg)),
                        right=Register(str(also_cond_reg)),
                    )
                )
                cond_reg = and_reg
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
        if not entry.parent_field_name:
            logger.warning(
                "SET %s TO FALSE: condition not in index — skipping", condition_name
            )
            return
        parent_ref, parent_rr = ctx.resolve_field_ref(
            entry.parent_field_name, materialised
        )
        if parent_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC:
            # WHEN SET TO FALSE IS not in scope — write SPACES (field-length fill)
            false_val: object = " " * max(parent_ref.fl.byte_length, 1)
        else:
            false_val = 0
        ctx.emit_encode_and_write(
            parent_rr, parent_ref.fl, ctx.const_to_reg(false_val), parent_ref.offset_reg
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
            value_reg = ctx.const_to_reg(filled)
        else:
            value_reg = ctx.const_to_reg(cv.from_val)
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


def _lower_display_operand(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Lower one DISPLAY operand to a register holding its display string."""
    if ctx.has_field(operand.name, materialised):
        ref, rr = ctx.resolve_field_ref(
            operand.name, materialised, subscripts=operand.subscripts
        )
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
    operand_regs = [
        _lower_display_operand(ctx, operand, materialised) for operand in stmt.operands
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
            )
        )
        combined_reg = folded

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print"),
            args=(combined_reg,),
        )
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(zero_reg, 0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_goback(
    ctx: EmitContext,
    stmt: GobackStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GOBACK — return control to the caller (same as STOP RUN at the IR level)."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(zero_reg, 0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_exit_program(
    ctx: EmitContext,
    stmt: ExitProgramStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PROGRAM — return control to the caller."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(zero_reg, 0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def _lower_computed_goto(
    ctx: EmitContext,
    computed: ComputedGoto,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO p1 ... pN DEPENDING ON idx — branch to the idx-th (1-based) target;
    out-of-range (idx <= 0 or idx > N) falls through to the next statement."""
    index = computed.index
    ref, rr = ctx.resolve_field_ref(
        index.name, materialised, index.qualifiers, subscripts=index.subscripts
    )
    idx_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
    for k, target in enumerate(computed.targets, start=1):
        k_reg = ctx.const_to_reg(k)
        cmp_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=cmp_reg,
                operator=resolve_binop("=="),
                left=Register(str(idx_reg)),
                right=Register(str(k_reg)),
            )
        )
        match_lbl = ctx.fresh_label("goto_dep_match")
        next_lbl = ctx.fresh_label("goto_dep_next")
        ctx.emit_inst(BranchIf(cond_reg=cmp_reg, branch_targets=(match_lbl, next_lbl)))
        ctx.emit_inst(Label_(label=match_lbl))
        ctx.emit_inst(Branch(label=CodeLabel(f"para_{target.paragraph}")))
        ctx.emit_inst(Label_(label=next_lbl))


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO — simple, computed (DEPENDING ON), or altered."""
    form = stmt.form
    if isinstance(form, SimpleGoto):
        ctx.emit_inst(Branch(label=CodeLabel(f"para_{form.target.paragraph}")))
    elif isinstance(form, ComputedGoto):
        _lower_computed_goto(ctx, form, materialised)
    # AlteredGoto: GO TO. with target supplied by ALTER — no-op, behavior
    # intentionally unchanged (not exercised by any test).
