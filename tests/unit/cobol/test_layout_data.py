"""The data-layout reader refuses a malformed layout Data."""

from __future__ import annotations

import pytest

from interpreter.cobol.layout_data import DATA_LAYOUT, field_positions
from interpreter.data_literals import boolean, integer, named, text
from interpreter.data_value import DataList, DataRecord
from interpreter.instructions import Data
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_boolean_where_the_layout_needs_an_integer_is_refused():
    entry = DataRecord(
        (
            named("name", text("WS-A")),
            named("offset", boolean(True)),
            named("length", integer(1)),
            named("category", text("ALPHANUMERIC")),
            named("total_digits", integer(1)),
            named("decimal_digits", integer(0)),
            named("signed", boolean(False)),
        )
    )
    malformed = Data(
        name=DATA_LAYOUT,
        value=DataRecord((named("fields", DataList((entry,))),)),
    )
    with pytest.raises(TypeError, match="layout field offset is not an integer"):
        field_positions((malformed,))
