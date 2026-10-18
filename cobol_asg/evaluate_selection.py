"""EVALUATE selection subjects and objects, read from the bridge's JSON."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from cobol_asg.abbreviated_condition import resolve_condition
from cobol_asg.any_object import AnyObject
from cobol_asg.cobol_expression import expr_from_dict
from cobol_asg.expression_subject import ExpressionSubject
from cobol_asg.range_object import RangeObject
from cobol_asg.selection_condition import SelectionCondition
from cobol_asg.truth_value import TruthValue
from cobol_asg.value_object import ValueObject

SelectionSubject = ExpressionSubject | SelectionCondition | TruthValue

SelectionObject = (
    AnyObject | TruthValue | SelectionCondition | ValueObject | RangeObject
)

_SUBJECTS: Mapping[str, Callable[[Mapping], SelectionSubject]] = {
    "expr": lambda d: ExpressionSubject(expr=expr_from_dict(d["expr"])),
    "condition": lambda d: SelectionCondition(
        condition=resolve_condition(d["condition"])
    ),
    "boolean": lambda d: TruthValue(value=bool(d["value"])),
}

_OBJECTS: Mapping[str, Callable[[Mapping], SelectionObject]] = {
    "any": lambda d: AnyObject(),
    "boolean": lambda d: TruthValue(
        value=bool(d["value"]) != bool(d.get("not", False))
    ),
    "condition": lambda d: SelectionCondition(
        condition=resolve_condition(d["condition"])
    ),
    "value": lambda d: ValueObject(
        value=expr_from_dict(d["value"]), negated=bool(d.get("not", False))
    ),
    "range": lambda d: RangeObject(
        low=expr_from_dict(d["from"]),
        high=expr_from_dict(d["thru"]),
        negated=bool(d.get("not", False)),
    ),
}


def selection_subject_from_dict(data: Mapping) -> SelectionSubject:
    return _SUBJECTS[str(data["kind"])](data)


def selection_object_from_dict(data: Mapping) -> SelectionObject:
    return _OBJECTS[str(data["kind"])](data)
