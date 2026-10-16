"""PERFORM statement lowering — simple, TIMES, UNTIL, VARYING variants."""

from __future__ import annotations

import logging

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
from interpreter.cobol.varying_labels import VaryingLabels, fresh_varying_labels
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


def _emit_until_test(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    label: CodeLabel,
    targets: tuple[CodeLabel, CodeLabel],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """At ``label``, go to targets[0] when the level's UNTIL holds, else targets[1]."""
    ctx.emit_inst(Label_(label=label), span=span)
    cond_reg = ctx.lower_condition(spec.condition, materialised, span=span)
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=targets), span=span)


def _emit_step(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    level: int,
    labels: VaryingLabels,
    then: CodeLabel,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """Augment one level, reset every level inside it to its FROM value, go on."""
    ctx.emit_inst(Label_(label=labels.steps[level]), span=span)
    emit_varying_increment(ctx, specs[level], materialised, span=span)
    for inner in specs[level + 1 :]:
        _init_varying_var(ctx, inner, materialised, span=span)
    ctx.emit_inst(Branch(label=then), span=span)


def _emit_test_before_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    specs: tuple[PerformVaryingSpec, ...],
    materialised: MaterialisedSectionedLayout,
) -> None:
    """TEST BEFORE: each level's UNTIL is tested outermost first before the body;
    a level whose UNTIL holds steps the level outside it, and the outermost one
    ends the PERFORM."""
    span = stmt.span
    labels = fresh_varying_labels(ctx, len(specs))
    when_done = (labels.exit, *labels.steps[:-1])
    when_not = (*labels.tests[1:], labels.body)
    for level, spec in enumerate(specs):
        _emit_until_test(
            ctx,
            spec,
            labels.tests[level],
            (when_done[level], when_not[level]),
            materialised,
            span=span,
        )
    ctx.emit_inst(Label_(label=labels.body), span=span)
    lower_perform_body(ctx, stmt, materialised)
    for stepped in reversed(range(len(specs))):
        _emit_step(
            ctx, specs, stepped, labels, labels.tests[stepped], materialised, span=span
        )
    ctx.emit_inst(Label_(label=labels.exit), span=span)


def _emit_test_after_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    specs: tuple[PerformVaryingSpec, ...],
    materialised: MaterialisedSectionedLayout,
) -> None:
    """TEST AFTER: after the body each level's UNTIL is tested innermost first;
    a level whose UNTIL does not hold is stepped and the body runs again, and
    the outermost one holding ends the PERFORM."""
    span = stmt.span
    labels = fresh_varying_labels(ctx, len(specs))
    when_done = (labels.exit, *labels.tests[:-1])
    ctx.emit_inst(Label_(label=labels.body), span=span)
    lower_perform_body(ctx, stmt, materialised)
    for level in reversed(range(len(specs))):
        _emit_until_test(
            ctx,
            specs[level],
            labels.tests[level],
            (when_done[level], labels.steps[level]),
            materialised,
            span=span,
        )
        _emit_step(ctx, specs, level, labels, labels.body, materialised, span=span)
    ctx.emit_inst(Label_(label=labels.exit), span=span)


def lower_perform_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... VARYING ... [AFTER ...]: every identifier is set to its FROM
    value, outermost first, before any UNTIL is tested."""
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)
    specs: tuple[PerformVaryingSpec, ...] = (spec, *spec.after_specs)
    for level in specs:
        _init_varying_var(ctx, level, materialised, span=stmt.span)
    if spec.test_before:
        _emit_test_before_varying(ctx, stmt, specs, materialised)
        return
    _emit_test_after_varying(ctx, stmt, specs, materialised)


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
