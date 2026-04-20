"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.cobol_expression import parse_expression
from interpreter.cobol.figurative_constants import translate_cobol_figurative
from interpreter.cobol.ref_mod import (
    RefModLiteral,
    RefModReference,
    RefModBinOp,
    RefModExpr,
)
from interpreter.cobol.cobol_statements import (
    ArithmeticStatement,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitStatement,
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
    result_reg: str,
    td: CobolTypeDescriptor,
) -> str:
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
            left=Register(str(result_reg)),
            right=Register(str(max_reg)),
        )
    )
    if td.signed:
        min_reg = ctx.const_to_reg(-max_val)
        under_min = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=under_min,
                operator=resolve_binop("<"),
                left=Register(str(result_reg)),
                right=Register(str(min_reg)),
            )
        )
        overflow_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=overflow_reg,
                operator=resolve_binop("or"),
                left=Register(str(over_max)),
                right=Register(str(under_min)),
            )
        )
        return overflow_reg
    return over_max


def emit_overflow_check(
    ctx: EmitContext,
    result_reg: str,
    td: CobolTypeDescriptor,
    on_size_err_label: CodeLabel,
    not_on_size_err_label: CodeLabel,
) -> None:
    """Emit overflow detection and BRANCH_IF to the supplied labels."""
    overflow_reg = _compute_overflow_flag(ctx, result_reg, td)
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(overflow_reg)),
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )


def eval_ref_mod_expr(
    ctx: EmitContext,
    expr: RefModExpr,
    layout: DataLayout,
    region_reg: str,
) -> str:
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
        if ctx.has_field(name, layout):
            field_ref = ctx.resolve_field_ref(name, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, field_ref.fl, field_ref.offset_reg
            )
            logging.debug(
                f"eval_ref_mod_expr: RefModReference {name} → decoded_reg={decoded_reg}"
            )
            # Return the decoded numeric value directly
            return decoded_reg
        else:
            # Unknown field: treat as literal numeric 0
            logging.debug(f"eval_ref_mod_expr: RefModReference {name} (unknown) → 0")
            return ctx.const_to_reg("0")

    elif isinstance(expr, RefModBinOp):
        # Binary operation: evaluate left and right, emit Binop
        left_reg = eval_ref_mod_expr(ctx, expr.left, layout, region_reg)
        right_reg = eval_ref_mod_expr(ctx, expr.right, layout, region_reg)
        result_reg = ctx.fresh_reg()

        op_str = expr.op
        binop_kind = resolve_binop(op_str)

        ctx.emit_inst(
            Binop(
                operator=binop_kind,
                left=Register(str(left_reg)),
                right=Register(str(right_reg)),
                result_reg=Register(str(result_reg)),
            )
        )
        return result_reg

    else:
        # Fallback: treat as literal zero
        return ctx.const_to_reg('"0"')


def lower_move(
    ctx: EmitContext,
    stmt: MoveStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """MOVE X [( start : length )] TO Y: handle reference modification."""
    target_ref = ctx.resolve_field_ref(stmt.target.name, layout, region_reg)

    # Get the source value (decode field or literal)
    if ctx.has_field(stmt.source.name, layout):
        source_ref = ctx.resolve_field_ref(stmt.source.name, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(
            region_reg, source_ref.fl, source_ref.offset_reg
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
        start_reg = eval_ref_mod_expr(
            ctx, stmt.source.ref_mod_start, layout, region_reg
        )
        # COBOL uses 1-indexed positions, but SLICE uses 0-indexed.
        # Convert: start_0indexed = start_1indexed - 1
        one_reg = ctx.const_to_reg("1")  # Numeric 1, not string "1"
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=Register(str(start_reg)),
                right=Register(str(one_reg)),
                result_reg=Register(str(start_0indexed_reg)),
            )
        )

        if stmt.source.ref_mod_length is not None:
            # Both start and length specified: SLICE operation
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, layout, region_reg
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
                    args=(
                        Register(str(value_str_reg)),
                        Register(str(start_0indexed_reg)),
                        Register(str(length_reg)),
                    ),
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
                    args=(
                        Register(str(value_str_reg)),
                        Register(str(start_0indexed_reg)),
                        Register(str(large_length)),
                    ),
                )
            )
            value_str_reg = result_reg

    # Handle target reference modification (write path): MOVE X TO Y(start:length)
    if stmt.target.ref_mod_start is not None:
        logging.debug(
            f"lower_move: Detected reference modification on target {stmt.target.name}: "
            f"start={stmt.target.ref_mod_start}, length={stmt.target.ref_mod_length}"
        )
        # Load current target field value as string (needed for SPLICE)
        target_decoded = ctx.emit_decode_field(
            region_reg, target_ref.fl, target_ref.offset_reg
        )
        target_str_reg = ctx.emit_to_string(target_decoded)

        # Evaluate target ref mod start; convert 1-indexed → 0-indexed
        tgt_start_reg = eval_ref_mod_expr(
            ctx, stmt.target.ref_mod_start, layout, region_reg
        )
        one_reg = ctx.const_to_reg("1")
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=Register(str(tgt_start_reg)),
                right=Register(str(one_reg)),
                result_reg=Register(str(tgt_start_0indexed_reg)),
            )
        )

        # Evaluate target ref mod length (or use large sentinel for "to end")
        if stmt.target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(
                ctx, stmt.target.ref_mod_length, layout, region_reg
            )
        else:
            tgt_length_reg = ctx.const_to_reg("999999")

        # Emit SPLICE: replace substring in target with source value
        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    Register(str(target_str_reg)),
                    Register(str(tgt_start_0indexed_reg)),
                    Register(str(tgt_length_reg)),
                    Register(str(value_str_reg)),
                ),
            )
        )
        value_str_reg = spliced_reg

    ctx.emit_encode_and_write(
        region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
    )


def lower_move_corresponding(
    ctx: EmitContext,
    stmt: MoveCorrespondingStatement,
    layout: DataLayout,
    region_reg: str,
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
    layout: DataLayout,
    region_reg: str,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
    if stmt.giving:
        lower_arithmetic_giving(ctx, stmt, layout, region_reg)
        return

    target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)

    if ctx.has_field(stmt.source, layout):
        source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
        src_decoded = ctx.emit_decode_field(
            region_reg, source_ref.fl, source_ref.offset_reg
        )
    else:
        src_decoded = ctx.const_to_reg(float(stmt.source))

    tgt_decoded = ctx.emit_decode_field(
        region_reg, target_ref.fl, target_ref.offset_reg
    )

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        op = ARITHMETIC_OPS[stmt.op]
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(op),
                left=Register(str(tgt_decoded)),
                right=Register(str(src_decoded)),
            )
        )
        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
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
                left=Register(str(src_decoded)),
                right=Register(str(zero_reg)),
            )
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(divzero_reg)),
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
            left=Register(str(tgt_decoded)),
            right=Register(str(src_decoded)),
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
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    result_str_reg = ctx.emit_to_string(result_reg)
    ctx.emit_encode_and_write(
        region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
    )
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_arithmetic_giving(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """MULTIPLY/DIVIDE X BY/INTO Y GIVING Z."""

    def _decode_operand(name: str) -> str:
        if ctx.has_field(name, layout):
            ref = ctx.resolve_field_ref(name, layout, region_reg)
            return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(float(name))

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
                left=Register(str(right_reg)),
                right=Register(str(zero_reg)),
            )
        )
        compute_label = ctx.fresh_label("divide_compute")
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(divzero_reg)),
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
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        )
    )

    if not has_clause:
        for giving_name in stmt.giving:
            giving_ref = ctx.resolve_field_ref(giving_name, layout, region_reg)
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, giving_ref.fl, result_str_reg, giving_ref.offset_reg
            )
        return

    # Compute combined overflow flag across all GIVING fields
    giving_refs = [ctx.resolve_field_ref(n, layout, region_reg) for n in stmt.giving]
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
        for ref in giving_refs
    ]
    combined_flag = overflow_flags[0]
    for flag in overflow_flags[1:]:
        new_combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_combined,
                operator=resolve_binop("or"),
                left=Register(str(combined_flag)),
                right=Register(str(flag)),
            )
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(combined_flag)),
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )

    ctx.emit_inst(Label_(label=on_size_err_label))
    for child in stmt.on_size_error:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    for ref in giving_refs:
        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(region_reg, ref.fl, result_str_reg, ref.offset_reg)
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    expr_tree = parse_expression(stmt.expression)
    result_reg = lower_expr_node(ctx, expr_tree, layout, region_reg)

    has_clause = bool(stmt.on_size_error or stmt.not_on_size_error)

    if not has_clause:
        result_str_reg = ctx.emit_to_string(result_reg)
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("COMPUTE target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
            )
        return

    on_size_err_label = ctx.fresh_label("on_size_err")
    not_on_size_err_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")

    # Resolve all valid targets up front
    target_refs = []
    for target_name in stmt.targets:
        if not ctx.has_field(target_name, layout):
            logger.warning("COMPUTE target %s not found in layout", target_name)
            continue
        target_refs.append(ctx.resolve_field_ref(target_name, layout, region_reg))

    # Guard: no valid targets means no writes and no overflow check — execute
    # not_on_size_error path (same as fast path: silent skip).
    if not target_refs:
        return

    # OR overflow flags across all targets (all-or-nothing semantics)
    overflow_flags = [
        _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
        for ref in target_refs
    ]
    combined_flag = overflow_flags[0]
    for flag in overflow_flags[1:]:
        new_combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_combined,
                operator=resolve_binop("or"),
                left=Register(str(combined_flag)),
                right=Register(str(flag)),
            )
        )
        combined_flag = new_combined

    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(combined_flag)),
            branch_targets=(on_size_err_label, not_on_size_err_label),
        )
    )

    ctx.emit_inst(Label_(label=on_size_err_label))
    for child in stmt.on_size_error:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=not_on_size_err_label))
    result_str_reg = ctx.emit_to_string(result_reg)
    for ref in target_refs:
        ctx.emit_encode_and_write(region_reg, ref.fl, result_str_reg, ref.offset_reg)
    for child in stmt.not_on_size_error:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_if(
    ctx: EmitContext,
    stmt: IfStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """IF condition ... [ELSE ...] END-IF."""
    cond_reg = ctx.lower_condition(stmt.condition, layout, region_reg)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(true_label, false_label),
        )
    )

    ctx.emit_inst(Label_(label=true_label))
    for child in stmt.children:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    for child in stmt.else_children:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_evaluate(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """EVALUATE subject WHEN value ..."""
    end_label = ctx.fresh_label("eval_end")

    for child in stmt.children:
        if isinstance(child, WhenStatement) and child.condition:
            if stmt.subject and stmt.subject.upper() != "TRUE":
                full_condition = f"{stmt.subject} = {child.condition}"
            else:
                full_condition = child.condition
            cond_reg = _lower_condition_str(
                ctx, full_condition, layout, region_reg, ctx._condition_index
            )
            when_true = ctx.fresh_label("when_true")
            when_false = ctx.fresh_label("when_false")
            ctx.emit_inst(
                BranchIf(
                    cond_reg=Register(str(cond_reg)),
                    branch_targets=(when_true, when_false),
                )
            )
            ctx.emit_inst(Label_(label=when_true))
            for grandchild in child.children:
                ctx.lower_statement(grandchild, layout, region_reg)
            ctx.emit_inst(Branch(label=end_label))
            ctx.emit_inst(Label_(label=when_false))
        elif isinstance(child, WhenOtherStatement):
            for grandchild in child.children:
                ctx.lower_statement(grandchild, layout, region_reg)

    ctx.emit_inst(Label_(label=end_label))


def lower_continue(
    ctx: EmitContext,
    stmt: ContinueStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """CONTINUE — no-op, emit nothing."""
    pass


def lower_exit(
    ctx: EmitContext,
    stmt: ExitStatement,
    layout: DataLayout,
    region_reg: str,
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
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INITIALIZE field1 field2 — reset to type-appropriate defaults.

    For group items, each elementary (leaf) child is reset with the
    type-appropriate default: spaces for ALPHANUMERIC, zeros for numeric.
    """
    for operand in stmt.operands:
        if not ctx.has_field(operand, layout):
            logger.warning("INITIALIZE target %s not found in layout", operand)
            continue
        ref = ctx.resolve_field_ref(operand, layout, region_reg)
        for leaf_fl in _leaf_fields_of(ref.fl, layout):
            leaf_ref = ctx.resolve_field_ref(leaf_fl.name, layout, region_reg)
            td = leaf_fl.type_descriptor
            if td.category == CobolDataCategory.ALPHANUMERIC:
                default = " " * td.total_digits
            else:
                default = "0"
            ctx.emit_field_encode(region_reg, leaf_fl, default, leaf_ref.offset_reg)


def lower_set(
    ctx: EmitContext,
    stmt: SetStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """SET target TO value / SET target UP|DOWN BY value."""
    if stmt.set_type == "TO":
        value_str = stmt.values[0] if stmt.values else "0"
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            value_str_reg = ctx.const_to_reg(str(value_str))
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
            )
    elif stmt.set_type == "BY":
        step_val = stmt.values[0] if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            tgt_decoded = ctx.emit_decode_field(
                region_reg, target_ref.fl, target_ref.offset_reg
            )
            step_reg = ctx.const_to_reg(ctx.parse_literal(step_val))
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(op),
                    left=Register(str(tgt_decoded)),
                    right=Register(str(step_reg)),
                )
            )
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
            )


def lower_display(
    ctx: EmitContext,
    stmt: DisplayStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """DISPLAY field-or-literal."""
    operand = stmt.operand

    if isinstance(operand, str) and ctx.has_field(operand, layout):
        ref = ctx.resolve_field_ref(operand, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        display_reg = ctx.emit_to_string(decoded_reg)
    else:
        display_reg = ctx.const_to_reg(str(operand))

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print"),
            args=(Register(str(display_reg)),),
        )
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """STOP RUN."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value=0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """GO TO paragraph-name."""
    ctx.emit_inst(Branch(label=CodeLabel(f"para_{stmt.target}")))
