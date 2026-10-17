"""DECIMAL-POINT IS COMMA applied to numeric literals as the ASG reader takes them in."""

from cobol_asg.asg_types import CobolASG
from cobol_asg.condition_name import ConditionValue

_WRITTEN = {
    "special_names": {"decimal_point_is_comma": True},
    "data_fields": [
        {
            "name": "WS-RATE",
            "level": 1,
            "pic": "9V9",
            "value": "2,5",
            "value_is_numeric": True,
            "conditions": [
                {
                    "name": "RATE-HALF",
                    "values": [{"from": "0,5", "to": "", "numeric": True}],
                }
            ],
        },
        {"name": "WS-EDITED", "level": 1, "pic": "9,99"},
        {
            "name": "WS-TEXT",
            "level": 1,
            "pic": "X(3)",
            "value": "1,5",
            "conditions": [{"name": "TEXT-ONE", "values": [{"from": "1,5"}]}],
        },
    ],
    "statements": [
        {"type": "MOVE", "operands": [{"name": "1,5"}, {"name": "WS-RATE"}]},
        {"type": "MOVE", "operands": [{"name": "-12,25E3"}, {"name": "A(1,2)"}]},
    ],
}


def test_numeric_literals_take_the_period_and_nothing_else_changes() -> None:
    asg = CobolASG.from_dict(_WRITTEN)
    rate, edited, text = asg.data_fields

    assert rate.value == "2.5"
    assert rate.conditions[0].values == [ConditionValue(from_val="0.5")]
    assert edited.pic == "9,99"
    assert text.value == "1,5"
    assert text.conditions[0].values == [ConditionValue(from_val="1,5")]
    assert [s.to_dict()["operands"] for s in asg.statements] == [
        [{"name": "1.5"}, {"name": "WS-RATE"}],
        [{"name": "-12.25E3"}, {"name": "A(1,2)"}],
    ]


def test_without_the_clause_literals_stay_as_written() -> None:
    asg = CobolASG.from_dict(_WRITTEN | {"special_names": {}})

    assert asg.data_fields[0].value == "2,5"
    assert asg.data_fields[0].conditions[0].values == [ConditionValue(from_val="0,5")]
    assert asg.statements[0].to_dict()["operands"] == [
        {"name": "1,5"},
        {"name": "WS-RATE"},
    ]
