"""The elementary items an INITIALIZE operand initialises: every occurrence of each
one, leaving out FILLER items and anything that redefines or lies under a
redefinition."""

from __future__ import annotations

from cobol_asg.cobol_expression import ExprNode, LiteralNode
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import DataItemMatch, DataLayout, FieldLayout
from interpreter.cobol.initialize_target import InitializeTarget

type DataItem = FieldLayout | DataLayout


def initialize_targets(
    operand: RefModOperand, match: DataItemMatch
) -> tuple[InitializeTarget, ...]:
    if isinstance(match.item, FieldLayout):
        return (InitializeTarget(match.item, operand),)
    enclosing = (match.name, *(name for name, _ in reversed(match.ancestors)))
    return _below(match.item, enclosing, operand.subscripts)


def _below(
    group: DataLayout, enclosing: tuple[str, ...], subscripts: tuple[ExprNode, ...]
) -> tuple[InitializeTarget, ...]:
    return tuple(
        target
        for name, item in (*group.fields.items(), *group.groups.items())
        if not (item.filler or item.redefines)
        for occurrence in _occurrences(item, subscripts)
        for target in _targets(name, item, enclosing, occurrence)
    )


def _occurrences(
    item: DataItem, subscripts: tuple[ExprNode, ...]
) -> tuple[tuple[ExprNode, ...], ...]:
    if item.occurs_count == 0:
        return (subscripts,)
    return tuple(
        (*subscripts, LiteralNode(str(number)))
        for number in range(1, item.occurs_count + 1)
    )


def _targets(
    name: str,
    item: DataItem,
    enclosing: tuple[str, ...],
    subscripts: tuple[ExprNode, ...],
) -> tuple[InitializeTarget, ...]:
    if isinstance(item, DataLayout):
        return _below(item, (name, *enclosing), subscripts)
    operand = RefModOperand(name=name, qualifiers=enclosing, subscripts=subscripts)
    return (InitializeTarget(item, operand),)
