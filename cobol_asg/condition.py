# pyright: standard
"""A COBOL condition as a typed tree, read from and written to the resolved JSON form.

The bridge writes a condition as nested JSON; ``abbreviated_condition`` first resolves
abbreviations and combined relations into AND/OR trees of plain tests, and this module
reads that resolved form. ``condition_to_dict`` writes it back, so a statement's
``to_dict`` still produces the JSON the parsed-ASG cache holds.

``negated`` is a test's NOT. A combination carries none: the bridge writes NOT on a
parenthesised combination as a ``Parenthesised`` around it.

A combination holds its operands flat. The bridge nests ``A OR B OR C`` on the
left, one level per operand, so a tree of pairs is as deep as the chain is long,
and walking it -- reading, writing, comparing -- recursed once per operand.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from functools import reduce
from itertools import accumulate, repeat, takewhile

from cobol_asg.cobol_expression import ExprNode, expr_from_dict, expr_to_dict


class Connective(Enum):
    AND = "AND"
    OR = "OR"


class RelationalOperator(Enum):
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER = ">"
    GREATER_OR_EQUAL = ">="
    LESS = "<"
    LESS_OR_EQUAL = "<="


class ClassKind(Enum):
    NUMERIC = "NUMERIC"
    ALPHABETIC = "ALPHABETIC"
    ALPHABETIC_LOWER = "ALPHABETIC-LOWER"
    ALPHABETIC_UPPER = "ALPHABETIC-UPPER"


class SignKind(Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ZERO = "ZERO"


@dataclass(frozen=True)
class Combination:
    """``operands`` joined by ``connective``, in the order written; two or more."""

    connective: Connective
    operands: tuple[Condition, ...]


@dataclass(frozen=True)
class RelationTest:
    left: ExprNode
    operator: RelationalOperator
    right: ExprNode
    negated: bool = False


@dataclass(frozen=True)
class ConditionNameTest:
    """A level-88 or switch-status condition name, as written."""

    name: str
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[ExprNode, ...] = ()
    negated: bool = False


@dataclass(frozen=True)
class ClassTest:
    operand: ExprNode
    kind: ClassKind
    negated: bool = False


@dataclass(frozen=True)
class UserClassTest:
    """``IS class-name``: a class the SPECIAL-NAMES CLASS clause declares."""

    operand: ExprNode
    class_name: str
    negated: bool = False


@dataclass(frozen=True)
class SignTest:
    operand: ExprNode
    kind: SignKind
    negated: bool = False


@dataclass(frozen=True)
class Parenthesised:
    inner: Condition
    negated: bool = False


@dataclass(frozen=True)
class UnparsedCondition:
    """A condition the bridge kept only as text: a bare data name, or a shape it
    does not structure. ``text`` is empty when it kept nothing."""

    text: str
    negated: bool = False


Condition = (
    Combination
    | RelationTest
    | ConditionNameTest
    | ClassTest
    | UserClassTest
    | SignTest
    | Parenthesised
    | UnparsedCondition
)


def _negated(d: Mapping) -> bool:
    return bool(d.get("not", False))


def _exprs(raw: Sequence[Mapping]) -> tuple[ExprNode, ...]:
    return tuple(expr_from_dict(item) for item in raw)


def _is_combination(d: Mapping | str) -> bool:
    return isinstance(d, Mapping) and "op" in d and "left" in d


def _combination(d: Mapping) -> Condition:
    """The left-nested run of one connective, read as one combination."""
    spine = tuple(
        takewhile(
            lambda node: _is_combination(node) and node["op"] == d["op"],
            accumulate(repeat(None), lambda node, _: node["left"], initial=d),
        )
    )
    return Combination(
        connective=Connective(d["op"]),
        operands=(
            condition_from_dict(spine[-1]["left"]),
            *(condition_from_dict(node["right"]) for node in reversed(spine)),
        ),
    )


def _condition_name(d: Mapping) -> Condition:
    return ConditionNameTest(
        name=str(d["condition_name"]),
        qualifiers=tuple(str(q) for q in d.get("condition_qualifiers", ())),
        subscripts=_exprs(d.get("condition_subscripts", ())),
        negated=_negated(d),
    )


def _parenthesised(d: Mapping) -> Condition:
    return Parenthesised(inner=condition_from_dict(d["condition"]), negated=_negated(d))


def _relation(d: Mapping) -> Condition:
    relation = d["relation"]
    return RelationTest(
        left=expr_from_dict(relation["left"]),
        operator=RelationalOperator(relation.get("op", "==")),
        right=expr_from_dict(relation["right"]),
        negated=_negated(d),
    )


def _user_class(d: Mapping) -> Condition:
    return UserClassTest(
        operand=expr_from_dict(d["operand"]),
        class_name=str(d["class_name"]),
        negated=_negated(d),
    )


def _class(d: Mapping) -> Condition:
    return ClassTest(
        operand=expr_from_dict(d["operand"]),
        kind=ClassKind(str(d["class"]).upper()),
        negated=_negated(d),
    )


def _sign(d: Mapping) -> Condition:
    return SignTest(
        operand=expr_from_dict(d["operand"]),
        kind=SignKind(str(d["sign"]).upper()),
        negated=_negated(d),
    )


_READERS: tuple[tuple[str, Callable[[Mapping], Condition]], ...] = (
    ("condition_name", _condition_name),
    ("condition", _parenthesised),
    ("relation", _relation),
    ("class_name", _user_class),
    ("class", _class),
    ("sign", _sign),
)


def condition_from_dict(d: Mapping | str) -> Condition:
    """The typed condition of a resolved condition dict; a bare string is unparsed text."""
    if isinstance(d, str):
        return UnparsedCondition(text=d)
    if _is_combination(d):
        return _combination(d)
    return next(
        (read(d) for field, read in _READERS if field in d),
        UnparsedCondition(text=str(d.get("text", "")), negated=_negated(d)),
    )


def _combination_dict(c: Combination) -> dict:
    return reduce(
        lambda left, right: {
            "op": c.connective.value,
            "left": left,
            "right": condition_to_dict(right),
        },
        c.operands[1:],
        condition_to_dict(c.operands[0]),
    )


def _relation_dict(c: RelationTest) -> dict:
    return {
        "not": c.negated,
        "relation": {
            "left": expr_to_dict(c.left),
            "op": c.operator.value,
            "right": expr_to_dict(c.right),
        },
    }


def _condition_name_dict(c: ConditionNameTest) -> dict:
    return {
        "not": c.negated,
        "condition_name": c.name,
        **(
            {"condition_subscripts": [expr_to_dict(s) for s in c.subscripts]}
            if c.subscripts
            else {}
        ),
        **({"condition_qualifiers": list(c.qualifiers)} if c.qualifiers else {}),
    }


def _class_dict(c: ClassTest) -> dict:
    return {"not": c.negated, "class": c.kind.value, "operand": expr_to_dict(c.operand)}


def _user_class_dict(c: UserClassTest) -> dict:
    return {
        "not": c.negated,
        "class_name": c.class_name,
        "operand": expr_to_dict(c.operand),
    }


def _sign_dict(c: SignTest) -> dict:
    return {"not": c.negated, "sign": c.kind.value, "operand": expr_to_dict(c.operand)}


def _parenthesised_dict(c: Parenthesised) -> dict:
    return {"not": c.negated, "condition": condition_to_dict(c.inner)}


def _unparsed_dict(c: UnparsedCondition) -> dict:
    return {"not": c.negated, "text": c.text}


_WRITERS: Mapping[type, Callable[..., dict]] = {
    Combination: _combination_dict,
    RelationTest: _relation_dict,
    ConditionNameTest: _condition_name_dict,
    ClassTest: _class_dict,
    UserClassTest: _user_class_dict,
    SignTest: _sign_dict,
    Parenthesised: _parenthesised_dict,
    UnparsedCondition: _unparsed_dict,
}


def condition_to_dict(c: Condition) -> dict:
    """The resolved JSON form of ``c``; ``condition_from_dict`` reads it back to ``c``."""
    return _WRITERS[type(c)](c)


def negated(c: Condition) -> Condition:
    """``c`` with NOT applied: a test's own NOT flips, a combination is wrapped."""
    if isinstance(c, Combination):
        return Parenthesised(inner=c, negated=True)
    return replace(c, negated=not c.negated)
