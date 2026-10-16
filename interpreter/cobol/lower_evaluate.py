"""EVALUATE lowering: each WHEN's selection objects against the selection subjects."""

from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from cobol_asg.any_object import AnyObject
from cobol_asg.cobol_expression import ExprNode, expr_to_dict
from cobol_asg.cobol_statements import (
    CobolStatementType,
    EvaluateStatement,
    WhenOtherStatement,
    WhenStatement,
)
from cobol_asg.evaluate_selection import SelectionObject, SelectionSubject
from cobol_asg.expression_subject import ExpressionSubject
from cobol_asg.range_object import RangeObject
from cobol_asg.selection_condition import SelectionCondition
from cobol_asg.truth_value import TruthValue
from cobol_asg.value_object import ValueObject
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.instructions import Binop, Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register


def lower_evaluate(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    end_label = ctx.fresh_label("eval_end")
    for child in stmt.children:
        _lower_evaluate_child(ctx, stmt, child, end_label, materialised)
    ctx.emit_inst(Label_(label=end_label), span=stmt.span)


def _lower_evaluate_child(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: CobolStatementType,
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    if isinstance(child, WhenStatement):
        _lower_when(ctx, stmt, child, end_label, materialised)
    elif isinstance(child, WhenOtherStatement):
        _lower_body(ctx, child.children, materialised)


def _lower_when(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = stmt.span
    cond_reg = _when_condition(ctx, stmt, child, materialised)
    when_true = ctx.fresh_label("when_true")
    when_false = ctx.fresh_label("when_false")
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(when_true, when_false)),
        span=span,
    )
    ctx.emit_inst(Label_(label=when_true), span=span)
    _lower_body(ctx, child.children, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=when_false), span=span)


def _lower_body(
    ctx: EmitContext,
    statements: Sequence[CobolStatementType],
    materialised: MaterialisedSectionedLayout,
) -> None:
    for statement in statements:
        ctx.lower_statement(statement, materialised)


def _when_condition(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    return reduce(
        lambda left, right: _combine(ctx, stmt, "or", left, right),
        (
            _when_alternative(ctx, stmt, alternative, materialised)
            for alternative in child.alternatives
        ),
        _when_alternative(ctx, stmt, child, materialised),
    )


def _when_alternative(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    child: WhenStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    pair_regs = [
        _selection_pair(ctx, stmt, subject, obj, materialised)
        for subject, obj in zip(stmt.subjects, child.objects, strict=False)
        if not isinstance(obj, AnyObject)
    ]
    return reduce(
        lambda left, right: _combine(ctx, stmt, "&&", left, right),
        pair_regs[1:],
        pair_regs[0] if pair_regs else ctx.const_to_reg(True, span=stmt.span),
    )


def _selection_pair(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    subject: SelectionSubject,
    obj: SelectionObject,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    if isinstance(subject, ExpressionSubject) and isinstance(
        obj, (ValueObject, RangeObject)
    ):
        return ctx.lower_condition(
            _value_test(subject.expr, obj), materialised, span=stmt.span
        )
    object_truth = _object_truth(ctx, stmt, obj, materialised)
    if isinstance(subject, ExpressionSubject):
        return object_truth
    subject_truth = _subject_truth(ctx, stmt, subject, materialised)
    return _combine(ctx, stmt, "==", subject_truth, object_truth)


def _value_test(subject: ExprNode, obj: ValueObject | RangeObject) -> dict:
    if isinstance(obj, ValueObject):
        return {"not": obj.negated, "relation": _relation(subject, "==", obj.value)}
    return {
        "not": obj.negated,
        "condition": {
            "op": "AND",
            "left": {"relation": _relation(subject, ">=", obj.low)},
            "right": {"relation": _relation(subject, "<=", obj.high)},
        },
    }


def _relation(left: ExprNode, op: str, right: ExprNode) -> dict:
    return {"left": expr_to_dict(left), "op": op, "right": expr_to_dict(right)}


def _subject_truth(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    subject: SelectionCondition | TruthValue,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    if isinstance(subject, TruthValue):
        return ctx.const_to_reg(subject.value, span=stmt.span)
    return ctx.lower_condition(subject.condition, materialised, span=stmt.span)


def _object_truth(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    obj: SelectionObject,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    if isinstance(obj, TruthValue):
        return ctx.const_to_reg(obj.value, span=stmt.span)
    if isinstance(obj, SelectionCondition):
        return ctx.lower_condition(obj.condition, materialised, span=stmt.span)
    raise ValueError(
        "An EVALUATE object answering TRUE, FALSE or a condition must be a "
        "condition, TRUE or FALSE"
    )


def _combine(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    operator: str,
    left: Register,
    right: Register,
) -> Register:
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(operator),
            left=left,
            right=right,
        ),
        span=stmt.span,
    )
    return result
