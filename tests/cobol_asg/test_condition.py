"""The typed condition tree read from, and written back to, the resolved JSON form."""

from collections.abc import Sequence
from functools import reduce

from cobol_asg.cobol_expression import (
    AddressOfNode,
    AllLiteralNode,
    FieldRefNode,
    FigurativeNode,
    LiteralNode,
    RefModNode,
)
from cobol_asg.condition import (
    ClassKind,
    ClassTest,
    Combination,
    ConditionNameTest,
    Connective,
    Parenthesised,
    RelationalOperator,
    RelationTest,
    SignKind,
    SignTest,
    UnparsedCondition,
    UserClassTest,
    condition_from_dict,
    condition_to_dict,
    negated,
)

A = {"kind": "ref", "name": "WS-A"}

RESOLVED = {
    "op": "OR",
    "left": {
        "op": "AND",
        "left": {
            "not": True,
            "condition_name": "IS-OPEN",
            "condition_qualifiers": ["WS-REC"],
            "condition_subscripts": [{"kind": "lit", "value": "2", "numeric": True}],
        },
        "right": {
            "not": False,
            "relation": {
                "left": {
                    "kind": "ref",
                    "name": "WS-B",
                    "ref_mod_start": {"kind": "lit", "value": "1"},
                },
                "op": "!=",
                "right": {"kind": "figurative", "value": "ALL", "literal": "'-'"},
            },
        },
    },
    "right": {
        "not": True,
        "condition": {
            "op": "AND",
            "left": {"not": False, "class": "NUMERIC", "operand": A},
            "right": {
                "op": "OR",
                "left": {"not": True, "class_name": "HEXDIGIT", "operand": A},
                "right": {
                    "op": "OR",
                    "left": {"not": False, "sign": "NEGATIVE", "operand": A},
                    "right": {
                        "not": False,
                        "relation": {
                            "left": {"kind": "address_of", "name": "WS-P"},
                            "op": "==",
                            "right": {"kind": "figurative", "value": "NULL"},
                        },
                    },
                },
            },
        },
    },
}

TYPED = Combination(
    Connective.OR,
    (
        Combination(
            Connective.AND,
            (
                ConditionNameTest(
                    name="IS-OPEN",
                    qualifiers=("WS-REC",),
                    subscripts=(LiteralNode(value="2", numeric=True),),
                    negated=True,
                ),
                RelationTest(
                    RefModNode(name="WS-B", ref_mod_start=LiteralNode(value="1")),
                    RelationalOperator.NOT_EQUAL,
                    AllLiteralNode(literal="'-'"),
                ),
            ),
        ),
        Parenthesised(
            inner=Combination(
                Connective.AND,
                (
                    ClassTest(FieldRefNode(name="WS-A"), ClassKind.NUMERIC),
                    Combination(
                        Connective.OR,
                        (
                            UserClassTest(
                                FieldRefNode(name="WS-A"), "HEXDIGIT", negated=True
                            ),
                            Combination(
                                Connective.OR,
                                (
                                    SignTest(
                                        FieldRefNode(name="WS-A"), SignKind.NEGATIVE
                                    ),
                                    RelationTest(
                                        AddressOfNode(name="WS-P"),
                                        RelationalOperator.EQUAL,
                                        FigurativeNode(value="NULL"),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            negated=True,
        ),
    ),
)


def _relation(value: str) -> dict:
    return {
        "not": False,
        "relation": {
            "left": A,
            "op": "==",
            "right": {"kind": "lit", "value": value},
        },
    }


def _left_nested(connective: str, operands: Sequence[dict]) -> dict:
    return reduce(
        lambda left, right: {"op": connective, "left": left, "right": right}, operands
    )


def test_every_resolved_shape_reads_into_its_typed_test():
    assert condition_from_dict(RESOLVED) == TYPED
    assert condition_from_dict({"not": True, "text": "WS-FLAG"}) == UnparsedCondition(
        text="WS-FLAG", negated=True
    )
    assert condition_from_dict({}) == UnparsedCondition(text="")
    assert condition_from_dict("WS-IDX = 5") == UnparsedCondition(text="WS-IDX = 5")


def test_writing_a_condition_reads_back_to_the_same_condition():
    assert condition_to_dict(TYPED) == RESOLVED
    assert condition_from_dict(condition_to_dict(TYPED)) == TYPED
    unparsed = UnparsedCondition(text="WS-FLAG", negated=True)
    assert condition_from_dict(condition_to_dict(unparsed)) == unparsed


def test_not_flips_a_test_and_wraps_a_combination():
    sign = SignTest(FieldRefNode(name="WS-A"), SignKind.ZERO)
    assert negated(sign) == SignTest(FieldRefNode(name="WS-A"), SignKind.ZERO, True)
    assert negated(negated(sign)) == sign
    assert negated(TYPED) == Parenthesised(inner=TYPED, negated=True)


def test_a_left_nested_chain_of_one_connective_is_one_combination():
    """However long: a member's chain of a few hundred operands overflowed the
    stack when each operand was a level of the tree."""
    chain = [_relation(str(i)) for i in range(5000)]
    written = _left_nested("OR", chain)
    read = condition_from_dict(written)
    assert read == Combination(
        Connective.OR, tuple(condition_from_dict(atom) for atom in chain)
    )
    assert condition_to_dict(read) == written
    mixed = _left_nested("OR", [_left_nested("AND", chain[:3]), chain[3]])
    assert condition_from_dict(mixed) == Combination(
        Connective.OR,
        (
            Combination(
                Connective.AND, tuple(condition_from_dict(a) for a in chain[:3])
            ),
            condition_from_dict(chain[3]),
        ),
    )
