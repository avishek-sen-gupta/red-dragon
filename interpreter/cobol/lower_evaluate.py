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
from interpreter.cobol.condition_lowering import lower_condition
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lowering_scope import LoweringScope
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
    scope = LoweringScope(ctx, materialised, stmt.span)
    end_label = ctx.fresh_label("eval_end")
    for child in stmt.children:
        _lower_evaluate_child(scope, stmt.subjects, child, end_label)
    ctx.emit_inst(Label_(label=end_label), span=stmt.span)


def _lower_evaluate_child(
    scope: LoweringScope,
    subjects: Sequence[SelectionSubject],
    child: CobolStatementType,
    end_label: CodeLabel,
) -> None:
    if isinstance(child, WhenStatement):
        _lower_when(scope, _when_condition(scope, subjects, child), child, end_label)
    elif isinstance(child, WhenOtherStatement):
        _lower_body(scope, child.children)


def _lower_when(
    scope: LoweringScope,
    cond_reg: Register,
    child: WhenStatement,
    end_label: CodeLabel,
) -> None:
    ctx, span = scope.ctx, scope.span
    when_true = ctx.fresh_label("when_true")
    when_false = ctx.fresh_label("when_false")
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(when_true, when_false)),
        span=span,
    )
    ctx.emit_inst(Label_(label=when_true), span=span)
    _lower_body(scope, child.children)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=when_false), span=span)


def _lower_body(scope: LoweringScope, statements: Sequence[CobolStatementType]) -> None:
    for statement in statements:
        scope.ctx.lower_statement(statement, scope.materialised)


def _when_condition(
    scope: LoweringScope,
    subjects: Sequence[SelectionSubject],
    child: WhenStatement,
) -> Register:
    return reduce(
        lambda left, right: _combine(scope, "or", left, right),
        (
            _when_alternative(scope, subjects, alternative)
            for alternative in child.alternatives
        ),
        _when_alternative(scope, subjects, child),
    )


def _when_alternative(
    scope: LoweringScope,
    subjects: Sequence[SelectionSubject],
    child: WhenStatement,
) -> Register:
    pair_regs = [
        _selection_pair(scope, subject, obj)
        for subject, obj in zip(subjects, child.objects, strict=False)
        if not isinstance(obj, AnyObject)
    ]
    return reduce(
        lambda left, right: _combine(scope, "&&", left, right),
        pair_regs[1:],
        pair_regs[0] if pair_regs else scope.ctx.const_to_reg(True, span=scope.span),
    )


def _selection_pair(
    scope: LoweringScope, subject: SelectionSubject, obj: SelectionObject
) -> Register:
    if isinstance(subject, ExpressionSubject) and isinstance(
        obj, (ValueObject, RangeObject)
    ):
        return lower_condition(scope, _value_test(subject.expr, obj))
    object_truth = _object_truth(scope, obj)
    if isinstance(subject, ExpressionSubject):
        return object_truth
    subject_truth = _subject_truth(scope, subject)
    return _combine(scope, "==", subject_truth, object_truth)


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
    scope: LoweringScope, subject: SelectionCondition | TruthValue
) -> Register:
    if isinstance(subject, TruthValue):
        return scope.ctx.const_to_reg(subject.value, span=scope.span)
    return lower_condition(scope, subject.condition)


def _object_truth(scope: LoweringScope, obj: SelectionObject) -> Register:
    if isinstance(obj, TruthValue):
        return scope.ctx.const_to_reg(obj.value, span=scope.span)
    if isinstance(obj, SelectionCondition):
        return lower_condition(scope, obj.condition)
    raise ValueError(
        "An EVALUATE object answering TRUE, FALSE or a condition must be a "
        "condition, TRUE or FALSE"
    )


def _combine(
    scope: LoweringScope, operator: str, left: Register, right: Register
) -> Register:
    result = scope.ctx.fresh_reg()
    scope.ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(operator),
            left=left,
            right=right,
        ),
        span=scope.span,
    )
    return result
