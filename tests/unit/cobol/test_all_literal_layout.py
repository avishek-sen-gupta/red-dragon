"""An ALL-literal VALUE and level-88 VALUE are sized to their item when laid out."""

from __future__ import annotations

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.figurative_constants import repeat_to_width
from tests.covers import covers


@covers(CobolFeature.FIGURATIVE_ALL)
def test_repeat_to_width_repeats_and_truncates_on_the_right() -> None:
    assert (
        repeat_to_width("AB", 7),
        repeat_to_width("ABC", 2),
        repeat_to_width("A", 1),
    ) == ("ABABABA", "AB", "A")


@covers(CobolFeature.FIGURATIVE_ALL, CobolFeature.LEVEL_88_CONDITION)
def test_layout_sizes_all_values_to_their_item() -> None:
    layout = build_data_layout(
        [
            CobolField.from_dict(
                {
                    "name": "W2",
                    "level": 1,
                    "pic": "X(5)",
                    "offset": 0,
                    "value": "AB",
                    "value_is_all": True,
                    "conditions": [
                        {
                            "name": "W2OK",
                            "values": [
                                {"from": "XY", "to": "", "all": True},
                                {"from": "Q", "to": ""},
                            ],
                        }
                    ],
                }
            ),
            CobolField.from_dict(
                {
                    "name": "GRP",
                    "level": 1,
                    "pic": "",
                    "offset": 5,
                    "value": "XYZ",
                    "value_is_all": True,
                    "children": [
                        {"name": "GA", "level": 2, "pic": "X(4)", "offset": 0},
                        {"name": "GB", "level": 2, "pic": "X(3)", "offset": 4},
                    ],
                }
            ),
            CobolField.from_dict(
                {
                    "name": "W3",
                    "level": 1,
                    "pic": "X(3)",
                    "offset": 12,
                    "value": "AB",
                }
            ),
        ]
    )
    w2 = layout.fields["W2"]
    assert (
        w2.value,
        [(v.from_val, v.to_val) for v in w2.conditions[0].values],
        layout.groups["GRP"].value,
        layout.fields["W3"].value,
    ) == ("ABABA", [("XYXYX", ""), ("Q", "")], "XYZXYZX", "AB")
