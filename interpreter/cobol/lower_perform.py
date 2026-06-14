"""PERFORM statement lowering — simple, TIMES, UNTIL, VARYING variants."""

from __future__ import annotations

import logging
from collections.abc import Callable

from interpreter.cobol.cobol_statements import (
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
)
from interpreter.cobol.condition_lowering import _lower_expr_dict
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Label_,
    LoadVar,
    SetContinuation,
    StoreVar,
)
from interpreter.continuation_name import ContinuationName
from interpreter.ir import CodeLabel
from interpreter.register import Register

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
    branch_label, continuation_key = resolve_perform_target(ctx, stmt)
    return_label = ctx.fresh_label("perform_return")
    ctx.emit_inst(
        SetContinuation(
            name=ContinuationName(str(continuation_key)), target_label=return_label
        )
    )
    ctx.emit_inst(Branch(label=branch_label))
    ctx.emit_inst(Label_(label=return_label))


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

    counter_var = ctx.fresh_name("__perform_ctr")
    loop_label = ctx.fresh_label("perform_times_loop")
    body_label = ctx.fresh_label("perform_times_body")
    exit_label = ctx.fresh_label("perform_times_exit")

    zero_reg = ctx.const_to_reg(0)
    ctx.emit_inst(
        StoreVar(name=VarName(counter_var), value_reg=Register(str(zero_reg)))
    )

    if ctx.has_field(spec.times, materialised):
        times_ref, times_rr = ctx.resolve_field_ref(spec.times, materialised)
        times_reg = ctx.emit_decode_field(times_rr, times_ref.fl, times_ref.offset_reg)
    else:
        times_reg = ctx.const_to_reg(ctx.parse_literal(spec.times))

    ctx.emit_inst(Label_(label=loop_label))
    ctr_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg, name=VarName(counter_var)))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop(">="),
            left=ctr_reg,
            right=Register(str(times_reg)),
        )
    )
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(exit_label, body_label),
        )
    )

    ctx.emit_inst(Label_(label=body_label))
    lower_perform_body(ctx, stmt, materialised)

    ctr_reg2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg2, name=VarName(counter_var)))
    one_reg = ctx.const_to_reg(1)
    inc_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=inc_reg,
            operator=resolve_binop("+"),
            left=ctr_reg2,
            right=Register(str(one_reg)),
        )
    )
    ctx.emit_inst(StoreVar(name=VarName(counter_var), value_reg=inc_reg))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=exit_label))


def lower_perform_until(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... UNTIL — condition-based loop."""
    spec = stmt.spec
    assert isinstance(spec, PerformUntilSpec)

    loop_label = ctx.fresh_label("perform_until_loop")
    body_label = ctx.fresh_label("perform_until_body")
    exit_label = ctx.fresh_label("perform_until_exit")

    if spec.test_before:
        ctx.emit_inst(Label_(label=loop_label))
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, body_label),
            )
        )
        ctx.emit_inst(Label_(label=body_label))
        lower_perform_body(ctx, stmt, materialised)
        ctx.emit_inst(Branch(label=loop_label))
        ctx.emit_inst(Label_(label=exit_label))
    else:
        ctx.emit_inst(Label_(label=loop_label))
        lower_perform_body(ctx, stmt, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, loop_label),
            )
        )
        ctx.emit_inst(Label_(label=exit_label))


def _init_varying_var(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Write spec.varying_from into spec.varying_var in the heap."""
    if not ctx.has_field(spec.varying_var, materialised):
        return
    varying_ref, varying_rr = ctx.resolve_field_ref(spec.varying_var, materialised)
    from_val_reg = _eval_varying_from(ctx, spec.varying_from, materialised)
    from_str_reg = ctx.emit_to_string(from_val_reg)
    ctx.emit_encode_and_write(
        varying_rr, varying_ref.fl, from_str_reg, varying_ref.offset_reg
    )


def _lower_perform_varying_single(
    ctx: EmitContext,
    stmt: PerformStatement,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Original single-variable PERFORM VARYING lowering — unchanged."""
    loop_label = ctx.fresh_label("perform_varying_loop")
    body_label = ctx.fresh_label("perform_varying_body")
    exit_label = ctx.fresh_label("perform_varying_exit")

    _init_varying_var(ctx, spec, materialised)

    if spec.test_before:
        ctx.emit_inst(Label_(label=loop_label))
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, body_label),
            )
        )
        ctx.emit_inst(Label_(label=body_label))
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised)
        ctx.emit_inst(Branch(label=loop_label))
        ctx.emit_inst(Label_(label=exit_label))
    else:
        ctx.emit_inst(Label_(label=loop_label))
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, loop_label),
            )
        )
        ctx.emit_inst(Label_(label=exit_label))


def _emit_test_before_level(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: Callable[[], None],
    when_done_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
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

    _init_varying_var(ctx, spec, materialised)

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_condition(spec.condition, materialised)
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(when_done_label, body_label),
        )
    )
    ctx.emit_inst(Label_(label=body_label))

    if specs[1:]:
        _emit_test_before_level(ctx, specs[1:], body_fn, incr_label, materialised)
    else:
        body_fn()

    ctx.emit_inst(Label_(label=incr_label))
    emit_varying_increment(ctx, spec, materialised)
    ctx.emit_inst(Branch(label=loop_label))


def _emit_test_after_varying(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: Callable[[], None],
    materialised: MaterialisedSectionedLayout,
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
        _init_varying_var(ctx, spec, materialised)

    # Body block
    ctx.emit_inst(Label_(label=body_label))
    body_fn()
    # Falls through to innermost increment (incr_labels[n-1])

    # Increment cascade: innermost (n-1) → outermost (0)
    for i in range(n - 1, -1, -1):
        spec = specs[i]
        ctx.emit_inst(Label_(label=incr_labels[i]))
        emit_varying_increment(ctx, spec, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)

        true_target = exit_label if i == 0 else incr_labels[i - 1]
        # Innermost (i == n-1): false → body directly (no inner vars to reset)
        false_target = body_label if i == n - 1 else continue_labels[i]

        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(true_target, false_target),
            )
        )

    # Continue blocks: reset exhausted inner variables, re-enter body
    for i in range(n - 2, -1, -1):
        ctx.emit_inst(Label_(label=continue_labels[i]))
        for j in range(i + 1, n):
            _init_varying_var(ctx, specs[j], materialised)
        ctx.emit_inst(Branch(label=body_label))

    ctx.emit_inst(Label_(label=exit_label))


def lower_perform_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)

    all_specs: tuple[PerformVaryingSpec, ...] = (spec,) + spec.after_specs

    if len(all_specs) == 1:
        _lower_perform_varying_single(ctx, stmt, spec, materialised)
    elif spec.test_before:
        exit_label = ctx.fresh_label("pv_exit")
        body_fn = lambda: lower_perform_body(ctx, stmt, materialised)
        _emit_test_before_level(ctx, all_specs, body_fn, exit_label, materialised)
        ctx.emit_inst(Label_(label=exit_label))
    else:
        _emit_test_after_varying(
            ctx,
            all_specs,
            lambda: lower_perform_body(ctx, stmt, materialised),
            materialised,
        )


def _eval_varying_from(
    ctx: EmitContext,
    varying_from: "str | dict",
    materialised: MaterialisedSectionedLayout,
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
                ref, _ = ctx.resolve_field_ref(name, materialised)
                return ctx.const_to_reg(ref.fl.byte_length)
            logger.warning("LENGTH OF unknown field %s — using 0", name)
            return ctx.const_to_reg(0)
        return _lower_expr_dict(ctx, varying_from, materialised)

    # Legacy text form (no structured node available).
    text = str(varying_from)
    if ctx.has_field(text, materialised):
        ref, rr = ctx.resolve_field_ref(text, materialised)
        return ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
    return ctx.const_to_reg(ctx.parse_literal(text))


def emit_varying_increment(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit IR to increment the VARYING variable by the BY value."""
    if not ctx.has_field(spec.varying_var, materialised):
        logger.warning("VARYING variable %s not found in layout", spec.varying_var)
        return

    varying_ref, varying_rr = ctx.resolve_field_ref(spec.varying_var, materialised)
    val_reg = ctx.emit_decode_field(varying_rr, varying_ref.fl, varying_ref.offset_reg)

    by_reg = ctx.const_to_reg(ctx.parse_literal(spec.varying_by))
    new_val_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_val_reg,
            operator=resolve_binop("+"),
            left=Register(str(val_reg)),
            right=Register(str(by_reg)),
        )
    )

    new_str_reg = ctx.emit_to_string(new_val_reg)
    ctx.emit_encode_and_write(
        varying_rr, varying_ref.fl, new_str_reg, varying_ref.offset_reg
    )
