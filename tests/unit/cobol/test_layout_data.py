"""The lowered data-layout Data reads back as the layout the frontend exposes."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.data_literals import boolean, integer, named, text
from interpreter.cobol.layout_data import DATA_LAYOUT, FieldPosition, field_positions
from interpreter.data_value import DataList, DataRecord
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import Data
from tests.covers import NotLanguageFeature, covers

_PROGRAMS = sorted(
    (
        Path(__file__).resolve().parents[3]
        / "proleap-bridge/src/test/resources/fixtures"
    ).glob("*.cbl")
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("program", _PROGRAMS, ids=[p.name for p in _PROGRAMS])
def test_field_positions_read_back_the_frontend_layout(program: Path):
    frontend = CobolFrontend(make_cobol_parser())
    instructions = frontend.lower(program.read_bytes())
    declarations = tuple(i for i in instructions if isinstance(i, Data))
    assert list(field_positions(declarations).items()) == [
        (name, FieldPosition(**entry)) for name, entry in frontend.data_layout.items()
    ]


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
