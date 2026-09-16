"""PERFORM statement lowering — simple, TIMES, UNTIL, VARYING variants."""

from __future__ import annotations

import logging
from collections.abc import Callable

from cobol_asg.cobol_statements import (
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
)
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.condition_lowering import _lower_expr_dict
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
    if stmt.children and stmt.spec is None:
        for child in stmt.children:
            ctx.lower_statement(child, materialised)
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
) -> tuple[CodeLabel, CodeLabel]:
    """Resolve branch-target label and continuation-key label for PERFORM."""
    target = stmt.target
    section_paras = ctx.section_paragraphs

    if target in section_paras:
        branch_label = CodeLabel(f"section_{target}")
        thru = stmt.thru
        if thru and thru in section_paras:
            continuation_key = CodeLabel(f"section_{thru}_end")
        elif thru:
            # THRU target is a paragraph, not a section. The perform range ends
            # *after that paragraph*, so the return continuation must be keyed on
            # the paragraph's end — not the FROM section's end. Keying it on the
            # section end mismatches the `resume_continuation para_{thru}_end`
            # that the paragraph emits, so control falls through to whatever
            # paragraph follows the THRU target instead of returning to PERFORM.
            continuation_key = CodeLabel(f"para_{thru}_end")
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
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit SET_CONTINUATION + BRANCH + return LABEL for a simple procedure PERFORM."""
    span = stmt.span
    branch_label, continuation_key = resolve_perform_target(ctx, stmt)
    return_label = ctx.fresh_label("perform_return")
    ctx.emit_inst(
        SetContinuation(
            name=ContinuationName(str(continuation_key)), target_label=return_label
        ),
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
        for child in stmt.children:
            ctx.lower_statement(child, materialised)
    elif stmt.target:
        emit_perform_branch(ctx, stmt, materialised)


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

    if ctx.has_field(spec.times, materialised):
        times_ref, times_rr = ctx.resolve_field_ref(spec.times, materialised, span=span)
        times_reg = ctx.emit_decode_field(
            times_rr,
            times_ref.fl,
            times_ref.offset_reg,
            extent=times_ref.extent,
            span=span,
        )
    else:
        times_reg = ctx.const_to_reg(ctx.parse_literal(spec.times), span=span)

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
    """Write spec.varying_from into spec.varying_var in the heap."""
    if not ctx.has_field(spec.varying_var, materialised):
        return
    varying_ref, varying_rr = ctx.resolve_field_ref(
        spec.varying_var, materialised, span=span
    )
    from_val_reg = _eval_varying_from(ctx, spec.varying_from, materialised, span=span)
    from_str_reg = ctx.emit_to_string(from_val_reg, span=span)
    ctx.emit_encode_and_write(
        varying_rr,
        varying_ref.fl,
        from_str_reg,
        varying_ref.offset_reg,
        extent=varying_ref.extent,
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

    all_specs: tuple[PerformVaryingSpec, ...] = (spec,) + spec.after_specs

    if len(all_specs) == 1:
        _lower_perform_varying_single(ctx, stmt, spec, materialised)
    elif spec.test_before:
        exit_label = ctx.fresh_label("pv_exit")
        body_fn = lambda: lower_perform_body(ctx, stmt, materialised)
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


def _eval_varying_from(
    ctx: EmitContext,
    varying_from: str | dict,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Evaluate a PERFORM VARYING FROM value to a numeric register.

    Handles the structured forms emitted by the bridge:
    - {"kind": "length_of", "name": "WS-S"} → the field's byte length (a const)
    - {"kind": "ref"/"lit"/"binop"/...}     → general expression lowering
      (a bare field decodes to its value, a literal to its const).

    A legacy flat-string FROM falls back to field-decode-or-literal.
    """
    if isinstance(varying_from, dict):
        if varying_from.get("kind") == "length_of":
            name = varying_from.get("name", "")
            if ctx.has_field(name, materialised):
                ref, _ = ctx.resolve_field_ref(name, materialised, span=span)
                return ctx.const_to_reg(ref.fl.byte_length, span=span)
            logger.warning("LENGTH OF unknown field %s — using 0", name)
            return ctx.const_to_reg(0, span=span)
        return _lower_expr_dict(ctx, varying_from, materialised, span=span)

    # Legacy text form (no structured node available).
    text = str(varying_from)
    if ctx.has_field(text, materialised):
        ref, rr = ctx.resolve_field_ref(text, materialised, span=span)
        return ctx.emit_decode_field(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
    return ctx.const_to_reg(ctx.parse_literal(text), span=span)


def emit_varying_increment(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Emit IR to increment the VARYING variable by the BY value."""
    if not ctx.has_field(spec.varying_var, materialised):
        logger.warning("VARYING variable %s not found in layout", spec.varying_var)
        return

    varying_ref, varying_rr = ctx.resolve_field_ref(
        spec.varying_var, materialised, span=span
    )
    val_reg = ctx.emit_decode_field(
        varying_rr,
        varying_ref.fl,
        varying_ref.offset_reg,
        extent=varying_ref.extent,
        span=span,
    )

    by_reg = ctx.const_to_reg(ctx.parse_literal(spec.varying_by), span=span)
    new_val_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_val_reg,
            operator=resolve_binop("+"),
            left=Register(str(val_reg)),
            right=Register(str(by_reg)),
        ),
        span=span,
    )

    new_str_reg = ctx.emit_to_string(new_val_reg, span=span)
    ctx.emit_encode_and_write(
        varying_rr,
        varying_ref.fl,
        new_str_reg,
        varying_ref.offset_reg,
        extent=varying_ref.extent,
        span=span,
    )
