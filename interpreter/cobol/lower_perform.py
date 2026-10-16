"""PERFORM statement lowering — simple, TIMES, UNTIL, VARYING variants."""

from __future__ import annotations

import logging
from collections.abc import Callable

from cobol_asg.cobol_expression import FieldRefNode
from cobol_asg.cobol_statements import (
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    ProcedureRef,
)
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Label_,
    LoadVar,
    SetContinuation,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def lower_perform(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM paragraph-name [THRU paragraph-name] [TIMES|UNTIL|VARYING]."""
    if not stmt.children:
        _lower_perform_form(ctx, stmt, materialised)
        return
    with ctx.in_inline_perform() as leave:
        _lower_perform_form(ctx, stmt, materialised)
    if ctx.exit_requested(leave):
        ctx.emit_inst(Label_(label=leave), span=stmt.span)


def _lower_perform_form(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    if stmt.children and stmt.spec is None:
        lower_perform_body(ctx, stmt, materialised)
        return

    if stmt.target and stmt.spec is None:
        emit_perform_branch(ctx, stmt, materialised)
        return

    if isinstance(stmt.spec, PerformTimesSpec):
        lower_perform_times(ctx, stmt, materialised)
    elif isinstance(stmt.spec, PerformUntilSpec):
        lower_perform_until(ctx, stmt, materialised)
    elif isinstance(stmt.spec, PerformVaryingSpec):
        lower_perform_varying(ctx, stmt, materialised)
    else:
        logger.warning("PERFORM with unknown spec: %s", stmt.spec)


def resolve_perform_target(
    ctx: EmitContext, stmt: PerformStatement
) -> tuple[CodeLabel, ContinuationName]:
    """The label PERFORM branches to, and the end of the last procedure in its
    range, where control returns."""
    first = ProcedureRef(paragraph=stmt.target, section=stmt.target_section)
    last = ProcedureRef(paragraph=stmt.thru, section=stmt.thru_section)
    return ctx.procedure_label(first), ctx.procedure_end(last if stmt.thru else first)


def emit_perform_branch(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit SET_CONTINUATION + BRANCH + return LABEL for a simple procedure PERFORM."""
    span = stmt.span
    branch_label, continuation_key = resolve_perform_target(ctx, stmt)
    return_label = ctx.fresh_label("perform_return")
    ctx.emit_inst(
        SetContinuation(name=continuation_key, target_label=return_label),
        span=span,
    )
    ctx.emit_inst(Branch(label=branch_label), span=span)
    ctx.emit_inst(Label_(label=return_label), span=span)


def lower_perform_body(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit the body of a PERFORM loop — inline children or procedure branch."""
    if stmt.children:
        _lower_inline_body(ctx, stmt, materialised)
    elif stmt.target:
        emit_perform_branch(ctx, stmt, materialised)


def _lower_inline_body(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    with ctx.in_perform_body() as cycle:
        for child in stmt.children:
            ctx.lower_statement(child, materialised)
    if ctx.exit_requested(cycle):
        ctx.emit_inst(Label_(label=cycle), span=stmt.span)


def lower_perform_times(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... TIMES — counter-based loop."""
    spec = stmt.spec
    assert isinstance(spec, PerformTimesSpec)
    span = stmt.span

    counter_var = ctx.fresh_name("__perform_ctr")
    loop_label = ctx.fresh_label("perform_times_loop")
    body_label = ctx.fresh_label("perform_times_body")
    exit_label = ctx.fresh_label("perform_times_exit")

    zero_reg = ctx.const_to_reg(0, span=span)
    ctx.emit_inst(
        StoreVar(name=VarName(counter_var), value_reg=Register(str(zero_reg))),
        span=span,
    )

    times_reg = lower_expr_node(ctx, spec.times, materialised, span=span)

    ctx.emit_inst(Label_(label=loop_label), span=span)
    ctr_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg, name=VarName(counter_var)), span=span)
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop(">="),
            left=ctr_reg,
            right=Register(str(times_reg)),
        ),
        span=span,
    )
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(exit_label, body_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=body_label), span=span)
    lower_perform_body(ctx, stmt, materialised)

    ctr_reg2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg2, name=VarName(counter_var)), span=span)
    one_reg = ctx.const_to_reg(1, span=span)
    inc_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=inc_reg,
            operator=resolve_binop("+"),
            left=ctr_reg2,
            right=Register(str(one_reg)),
        ),
        span=span,
    )
    ctx.emit_inst(StoreVar(name=VarName(counter_var), value_reg=inc_reg), span=span)
    ctx.emit_inst(Branch(label=loop_label), span=span)

    ctx.emit_inst(Label_(label=exit_label), span=span)


def lower_perform_until(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... UNTIL — condition-based loop."""
    spec = stmt.spec
    assert isinstance(spec, PerformUntilSpec)
    span = stmt.span

    loop_label = ctx.fresh_label("perform_until_loop")
    body_label = ctx.fresh_label("perform_until_body")
    exit_label = ctx.fresh_label("perform_until_exit")

    if spec.test_before:
        ctx.emit_inst(Label_(label=loop_label), span=span)
        cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, body_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=body_label), span=span)
        lower_perform_body(ctx, stmt, materialised)
        ctx.emit_inst(Branch(label=loop_label), span=span)
        ctx.emit_inst(Label_(label=exit_label), span=span)
    else:
        ctx.emit_inst(Label_(label=loop_label), span=span)
        lower_perform_body(ctx, stmt, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, loop_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=exit_label), span=span)


def _init_varying_var(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Store the FROM value in the VARYING identifier."""
    from_reg = lower_expr_node(ctx, spec.varying_from, materialised, span=span)
    _store_varying_var(ctx, spec.varying_var, from_reg, materialised, span=span)


def _store_varying_var(
    ctx: EmitContext,
    var: FieldRefNode,
    value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Write a numeric value to the VARYING identifier, at its subscripted occurrence."""
    ref, region_reg = ctx.resolve_field_ref(
        var.name,
        materialised,
        qualifiers=var.qualifiers,
        subscripts=var.subscripts,
        span=span,
    )
    ctx.emit_encode_and_write(
        region_reg,
        ref.fl,
        ctx.emit_to_string(value_reg, span=span),
        ref.offset_reg,
        extent=ref.extent,
        span=span,
    )


def _lower_perform_varying_single(
    ctx: EmitContext,
    stmt: PerformStatement,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Original single-variable PERFORM VARYING lowering — unchanged."""
    span = stmt.span
    loop_label = ctx.fresh_label("perform_varying_loop")
    body_label = ctx.fresh_label("perform_varying_body")
    exit_label = ctx.fresh_label("perform_varying_exit")

    _init_varying_var(ctx, spec, materialised, span=span)

    if spec.test_before:
        ctx.emit_inst(Label_(label=loop_label), span=span)
        cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, body_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=body_label), span=span)
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised, span=span)
        ctx.emit_inst(Branch(label=loop_label), span=span)
        ctx.emit_inst(Label_(label=exit_label), span=span)
    else:
        ctx.emit_inst(Label_(label=loop_label), span=span)
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised, span=span)
        cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, loop_label),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=exit_label), span=span)


def _emit_test_before_level(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: Callable[[], None],
    when_done_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Emit one level of a TEST BEFORE VARYING … AFTER … nested loop.

    specs[0] is the current level's variable; specs[1:] are inner AFTER variables.
    when_done_label is where to jump when this level's UNTIL fires — the caller
    passes either the whole-loop exit (outermost call) or the parent's incr label
    (inner calls), so a fired inner UNTIL cascades to the parent increment rather
    than exiting the whole PERFORM.
    """
    spec = specs[0]
    loop_label = ctx.fresh_label("pv_loop")
    body_label = ctx.fresh_label("pv_body")
    incr_label = ctx.fresh_label("pv_incr")

    _init_varying_var(ctx, spec, materialised, span=span)

    ctx.emit_inst(Label_(label=loop_label), span=span)
    cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(when_done_label, body_label),
        ),
        span=span,
    )
    ctx.emit_inst(Label_(label=body_label), span=span)

    if specs[1:]:
        _emit_test_before_level(
            ctx, specs[1:], body_fn, incr_label, materialised, span=span
        )
    else:
        body_fn()

    ctx.emit_inst(Label_(label=incr_label), span=span)
    emit_varying_increment(ctx, spec, materialised, span=span)
    ctx.emit_inst(Branch(label=loop_label), span=span)


def _emit_test_after_varying(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: Callable[[], None],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Emit a TEST AFTER VARYING … AFTER … nested loop.

    specs[0] is the outermost (primary VARYING); specs[-1] is the innermost
    (last AFTER). All variables are initialized before the body. After the
    body, increments cascade from innermost to outermost. When an outer UNTIL
    does not fire (loop continues), all exhausted inner variables are reset.

    IR shape (2-level example, I outer, J inner):
        init I; init J
        body_label:
          [body]
          # fall through to innermost incr
        incr_J:
          J += BY_J; if UNTIL_J → incr_I; else → body_label
        incr_I:
          I += BY_I; if UNTIL_I → exit; else → continue_I
        continue_I:
          J = FROM_J; → body_label
        exit_label:
    """
    n = len(specs)
    body_label = ctx.fresh_label("pv_body")
    exit_label = ctx.fresh_label("pv_exit")
    incr_labels = tuple(ctx.fresh_label("pv_incr") for _ in range(n))
    # continue_labels[i]: reset specs[i+1..n-1] to FROM, then jump to body.
    # Only needed for levels 0..n-2; the innermost (i=n-1) loops back to body directly.
    continue_labels = tuple(ctx.fresh_label("pv_continue") for _ in range(n - 1))

    # Initialise all variables (outermost first)
    for spec in specs:
        _init_varying_var(ctx, spec, materialised, span=span)

    # Body block
    ctx.emit_inst(Label_(label=body_label), span=span)
    body_fn()
    # Falls through to innermost increment (incr_labels[n-1])

    # Increment cascade: innermost (n-1) → outermost (0)
    for i in range(n - 1, -1, -1):
        spec = specs[i]
        ctx.emit_inst(Label_(label=incr_labels[i]), span=span)
        emit_varying_increment(ctx, spec, materialised, span=span)
        cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)

        true_target = exit_label if i == 0 else incr_labels[i - 1]
        # Innermost (i == n-1): false → body directly (no inner vars to reset)
        false_target = body_label if i == n - 1 else continue_labels[i]

        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(true_target, false_target),
            ),
            span=span,
        )

    # Continue blocks: reset exhausted inner variables, re-enter body
    for i in range(n - 2, -1, -1):
        ctx.emit_inst(Label_(label=continue_labels[i]), span=span)
        for j in range(i + 1, n):
            _init_varying_var(ctx, specs[j], materialised, span=span)
        ctx.emit_inst(Branch(label=body_label), span=span)

    ctx.emit_inst(Label_(label=exit_label), span=span)


def lower_perform_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)
    span = stmt.span

    all_specs: tuple[PerformVaryingSpec, ...] = (spec, *spec.after_specs)

    if len(all_specs) == 1:
        _lower_perform_varying_single(ctx, stmt, spec, materialised)
    elif spec.test_before:
        exit_label = ctx.fresh_label("pv_exit")

        def body_fn():
            return lower_perform_body(ctx, stmt, materialised)

        _emit_test_before_level(
            ctx, all_specs, body_fn, exit_label, materialised, span=span
        )
        ctx.emit_inst(Label_(label=exit_label), span=span)
    else:
        _emit_test_after_varying(
            ctx,
            all_specs,
            lambda: lower_perform_body(ctx, stmt, materialised),
            materialised,
            span=span,
        )


def emit_varying_increment(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Augment the VARYING identifier by the BY value."""
    val_reg = lower_expr_node(ctx, spec.varying_var, materialised, span=span)
    by_reg = lower_expr_node(ctx, spec.varying_by, materialised, span=span)
    new_val_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_val_reg,
            operator=resolve_binop("+"),
            left=val_reg,
            right=by_reg,
        ),
        span=span,
    )
    _store_varying_var(ctx, spec.varying_var, new_val_reg, materialised, span=span)
