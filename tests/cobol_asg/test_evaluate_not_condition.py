"""WHEN NOT condition-name arrives with its NOT as written; the ASG reader applies it."""

from cobol_asg.evaluate_selection import selection_object_from_dict
from cobol_asg.selection_condition import SelectionCondition

_NAME = {"not": False, "condition_name": "FLAG-ON"}
_PAIR = {
    "first": {"not": False, "condition_name": "A"},
    "rest": [{"bool": "OR", "atom": {"not": False, "condition_name": "B"}}],
}


def test_not_negates_the_condition_it_precedes() -> None:
    assert [
        selection_object_from_dict({"kind": "condition", "condition": _NAME}),
        selection_object_from_dict(
            {"kind": "condition", "not": True, "condition": _NAME}
        ),
        selection_object_from_dict(
            {"kind": "condition", "not": True, "condition": _PAIR}
        ),
        selection_object_from_dict(
            {"kind": "condition", "not": True, "condition": {**_NAME, "not": True}}
        ),
    ] == [
        SelectionCondition(condition=_NAME),
        SelectionCondition(condition={"not": True, "condition_name": "FLAG-ON"}),
        SelectionCondition(
            condition={
                "not": True,
                "condition": {
                    "op": "OR",
                    "left": {"not": False, "condition_name": "A"},
                    "right": {"not": False, "condition_name": "B"},
                },
            }
        ),
        SelectionCondition(condition=_NAME),
    ]
