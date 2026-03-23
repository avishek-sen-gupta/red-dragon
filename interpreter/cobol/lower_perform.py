"""PERFORM statement lowering — simple, TIMES, UNTIL, VARYING variants."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
)
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.ir import Opcode, CodeLabel

logger = logging.getLogger(__name__)


def lower_perform(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """PERFORM paragraph-name [THRU paragraph-name] [TIMES|UNTIL|VARYING]."""
    if stmt.children and stmt.spec is None:
        for child in stmt.children:
            ctx.lower_statement(child, layout, region_reg)
        return

    if stmt.target and stmt.spec is None:
        emit_perform_branch(ctx, stmt, layout, region_reg)
        return

    if isinstance(stmt.spec, PerformTimesSpec):
        lower_perform_times(ctx, stmt, layout, region_reg)
    elif isinstance(stmt.spec, PerformUntilSpec):
        lower_perform_until(ctx, stmt, layout, region_reg)
    elif isinstance(stmt.spec, PerformVaryingSpec):
        lower_perform_varying(ctx, stmt, layout, region_reg)
    else:
        logger.warning("PERFORM with unknown spec: %s", stmt.spec)


def resolve_perform_target(ctx: EmitContext, stmt: PerformStatement) -> tuple[CodeLabel, CodeLabel]:
    """Resolve branch-target label and continuation-key label for PERFORM."""
    target = stmt.target
    section_paras = ctx.section_paragraphs

    if target in section_paras:
        branch_label = CodeLabel(f"section_{target}")
        thru = stmt.thru
        if thru and thru in section_paras:
            continuation_key = CodeLabel(f"section_{thru}_end")
        else:
            continuation_key = CodeLabel(f"section_{target}_end")
        return branch_label, continuation_key

    thru_name = stmt.thru if stmt.thru else target
    branch_label = CodeLabel(f"para_{target}")
    continuation_key = CodeLabel(f"para_{thru_name}_end")
    return branch_label, continuation_key


def emit_perform_branch(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Emit SET_CONTINUATION + BRANCH + return LABEL for a simple procedure PERFORM."""
    branch_label, continuation_key = resolve_perform_target(ctx, stmt)
    return_label = ctx.fresh_label("perform_return")
    ctx.emit(
        Opcode.SET_CONTINUATION,
        operands=[continuation_key, return_label],
    )
    ctx.emit(Opcode.BRANCH, label=branch_label)
    ctx.emit(Opcode.LABEL, label=return_label)


def lower_perform_body(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Emit the body of a PERFORM loop — inline children or procedure branch."""
    if stmt.children:
        for child in stmt.children:
            ctx.lower_statement(child, layout, region_reg)
    elif stmt.target:
        emit_perform_branch(ctx, stmt, layout, region_reg)


def lower_perform_times(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """PERFORM ... TIMES — counter-based loop."""
    spec = stmt.spec
    assert isinstance(spec, PerformTimesSpec)

    counter_var = ctx.fresh_name("__perform_ctr")
    loop_label = ctx.fresh_label("perform_times_loop")
    body_label = ctx.fresh_label("perform_times_body")
    exit_label = ctx.fresh_label("perform_times_exit")

    zero_reg = ctx.const_to_reg(0)
    ctx.emit(Opcode.STORE_VAR, operands=[counter_var, zero_reg])

    if ctx.has_field(spec.times, layout):
        times_ref = ctx.resolve_field_ref(spec.times, layout, region_reg)
        times_reg = ctx.emit_decode_field(
            region_reg, times_ref.fl, times_ref.offset_reg
        )
    else:
        times_reg = ctx.const_to_reg(ctx.parse_literal(spec.times))

    ctx.emit(Opcode.LABEL, label=loop_label)
    ctr_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg, operands=[counter_var])
    cond_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=cond_reg,
        operands=[">=", ctr_reg, times_reg],
    )
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=CodeLabel(f"{exit_label},{body_label}"),
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    lower_perform_body(ctx, stmt, layout, region_reg)

    ctr_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg2, operands=[counter_var])
    one_reg = ctx.const_to_reg(1)
    inc_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=inc_reg, operands=["+", ctr_reg2, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[counter_var, inc_reg])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=exit_label)


def lower_perform_until(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """PERFORM ... UNTIL — condition-based loop."""
    spec = stmt.spec
    assert isinstance(spec, PerformUntilSpec)

    loop_label = ctx.fresh_label("perform_until_loop")
    body_label = ctx.fresh_label("perform_until_body")
    exit_label = ctx.fresh_label("perform_until_exit")

    if spec.test_before:
        ctx.emit(Opcode.LABEL, label=loop_label)
        cond_reg = ctx.lower_condition(spec.condition, layout, region_reg)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{exit_label},{body_label}"),
        )
        ctx.emit(Opcode.LABEL, label=body_label)
        lower_perform_body(ctx, stmt, layout, region_reg)
        ctx.emit(Opcode.BRANCH, label=loop_label)
        ctx.emit(Opcode.LABEL, label=exit_label)
    else:
        ctx.emit(Opcode.LABEL, label=loop_label)
        lower_perform_body(ctx, stmt, layout, region_reg)
        cond_reg = ctx.lower_condition(spec.condition, layout, region_reg)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{exit_label},{loop_label}"),
        )
        ctx.emit(Opcode.LABEL, label=exit_label)


def lower_perform_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)

    loop_label = ctx.fresh_label("perform_varying_loop")
    body_label = ctx.fresh_label("perform_varying_body")
    exit_label = ctx.fresh_label("perform_varying_exit")

    if ctx.has_field(spec.varying_var, layout):
        varying_ref = ctx.resolve_field_ref(spec.varying_var, layout, region_reg)
        from_str_reg = ctx.const_to_reg(str(spec.varying_from))
        ctx.emit_encode_and_write(
            region_reg, varying_ref.fl, from_str_reg, varying_ref.offset_reg
        )

    if spec.test_before:
        ctx.emit(Opcode.LABEL, label=loop_label)
        cond_reg = ctx.lower_condition(spec.condition, layout, region_reg)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{exit_label},{body_label}"),
        )
        ctx.emit(Opcode.LABEL, label=body_label)
        lower_perform_body(ctx, stmt, layout, region_reg)
        emit_varying_increment(ctx, spec, layout, region_reg)
        ctx.emit(Opcode.BRANCH, label=loop_label)
        ctx.emit(Opcode.LABEL, label=exit_label)
    else:
        ctx.emit(Opcode.LABEL, label=loop_label)
        lower_perform_body(ctx, stmt, layout, region_reg)
        emit_varying_increment(ctx, spec, layout, region_reg)
        cond_reg = ctx.lower_condition(spec.condition, layout, region_reg)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{exit_label},{loop_label}"),
        )
        ctx.emit(Opcode.LABEL, label=exit_label)


def emit_varying_increment(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Emit IR to increment the VARYING variable by the BY value."""
    if not ctx.has_field(spec.varying_var, layout):
        logger.warning("VARYING variable %s not found in layout", spec.varying_var)
        return

    varying_ref = ctx.resolve_field_ref(spec.varying_var, layout, region_reg)
    val_reg = ctx.emit_decode_field(region_reg, varying_ref.fl, varying_ref.offset_reg)

    by_reg = ctx.const_to_reg(ctx.parse_literal(spec.varying_by))
    new_val_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=new_val_reg,
        operands=["+", val_reg, by_reg],
    )

    new_str_reg = ctx.emit_to_string(new_val_reg)
    ctx.emit_encode_and_write(
        region_reg, varying_ref.fl, new_str_reg, varying_ref.offset_reg
    )
