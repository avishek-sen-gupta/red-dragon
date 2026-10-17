"""A VALUE clause's numeric-literal fact reaches the elementary item's layout."""

from __future__ import annotations

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


@covers(CobolFeature.VALUE_CLAUSE, CobolFeature.NUMERIC_EDITED)
def test_layout_keeps_whether_the_value_literal_is_numeric() -> None:
    numeric = CobolField.from_dict(
        {
            "name": "E1",
            "level": 1,
            "pic": "ZZ9.99",
            "offset": 0,
            "value": "12.5",
            "value_is_numeric": True,
        }
    )
    nonnumeric = CobolField.from_dict(
        {"name": "E2", "level": 1, "pic": "ZZ9.99", "offset": 6, "value": "12.5"}
    )
    layout = build_data_layout([numeric, nonnumeric])
    assert (
        layout.fields["E1"].value_is_numeric,
        layout.fields["E2"].value_is_numeric,
        numeric.to_dict()["value_is_numeric"],
        "value_is_numeric" in nonnumeric.to_dict(),
    ) == (True, False, True, False)
