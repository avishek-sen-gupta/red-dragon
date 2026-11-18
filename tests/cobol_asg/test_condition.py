"""The typed condition tree read from, and written back to, the resolved JSON form."""

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
    Combination(
        Connective.AND,
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
    Parenthesised(
        inner=Combination(
            Connective.AND,
            ClassTest(FieldRefNode(name="WS-A"), ClassKind.NUMERIC),
            Combination(
                Connective.OR,
                UserClassTest(FieldRefNode(name="WS-A"), "HEXDIGIT", negated=True),
                Combination(
                    Connective.OR,
                    SignTest(FieldRefNode(name="WS-A"), SignKind.NEGATIVE),
                    RelationTest(
                        AddressOfNode(name="WS-P"),
                        RelationalOperator.EQUAL,
                        FigurativeNode(value="NULL"),
                    ),
                ),
            ),
        ),
        negated=True,
    ),
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
