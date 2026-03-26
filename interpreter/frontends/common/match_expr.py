"""Unified match expression lowering framework.

Provides lower_match_as_expr() which emits IR for expression-style match
statements that return a value. Language frontends provide callbacks via
MatchArmSpec to handle language-specific tree-sitter node extraction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.frontends.common.patterns import (
    CapturePattern,
    Pattern,
    WildcardPattern,
    compile_pattern_bindings,
    compile_pattern_test,
    _needs_pre_guard_bindings,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.register import Register
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    DeclVar,
    Label_,
    LoadVar,
)


@dataclass(frozen=True)
class MatchArmSpec:
    """Language-specific callbacks for decomposing match/switch arms.

    extract_arms: (body_node) -> list of arm nodes
    pattern_of:   (ctx, arm) -> Pattern ADT
    guard_of:     (ctx, arm) -> guard expression node or None
    body_of:      (ctx, arm) -> result register (lowers body as expression)
    """

    extract_arms: Callable[[object], list[object]]
    pattern_of: Callable[[TreeSitterEmitContext, object], Pattern]
    guard_of: Callable[[TreeSitterEmitContext, object], object | None]
    body_of: Callable[[TreeSitterEmitContext, object], str]


def lower_match_as_expr(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    body_node: object,
    spec: MatchArmSpec,
) -> Register:
    """Emit IR for expression-style match. Returns result register."""
    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")

    for arm in spec.extract_arms(body_node):
        _lower_arm(ctx, arm, subject_reg, result_var, end_label, spec)

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=result_var))
    return reg


def _lower_arm(
    ctx: TreeSitterEmitContext,
    arm: object,
    subject_reg: str,
    result_var: str,
    end_label: str,
    spec: MatchArmSpec,
) -> None:
    """Lower a single arm: test pattern, bind, evaluate body, store result."""
    pattern = spec.pattern_of(ctx, arm)
    guard_node = spec.guard_of(ctx, arm)

    is_irrefutable = (
        isinstance(pattern, (WildcardPattern, CapturePattern)) and guard_node is None
    )

    if is_irrefutable:
        compile_pattern_bindings(ctx, subject_reg, pattern)
        body_reg = spec.body_of(ctx, arm)
        ctx.emit_inst(DeclVar(name=result_var, value_reg=str(body_reg)))
        ctx.emit_inst(Branch(label=end_label))
        return

    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    if guard_node:
        if _needs_pre_guard_bindings(pattern):
            compile_pattern_bindings(ctx, subject_reg, pattern)
        guard_reg = ctx.lower_expr(guard_node)
        final_test = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=final_test,
                operator=resolve_binop("&&"),
                left=str(test_reg),
                right=str(guard_reg),
            ),
        )
        test_reg = final_test

    arm_label = ctx.fresh_label("match_arm")
    next_label = ctx.fresh_label("match_next")
    ctx.emit_inst(
        BranchIf(
            cond_reg=str(test_reg),
            branch_targets=(arm_label, next_label),
        ),
    )
    ctx.emit_inst(Label_(label=arm_label))

    if not (guard_node and _needs_pre_guard_bindings(pattern)):
        compile_pattern_bindings(ctx, subject_reg, pattern)

    body_reg = spec.body_of(ctx, arm)
    ctx.emit_inst(DeclVar(name=result_var, value_reg=str(body_reg)))
    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=next_label))
