"""The lowered data-layout Data reads back as the layout the frontend exposes."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.layout_data import FieldPosition, field_positions
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
    assert field_positions(declarations) == {
        name: FieldPosition(**entry) for name, entry in frontend.data_layout.items()
    }
