"""The bridge's ASG for a program is the same on every parse: it carries no clock."""

from __future__ import annotations

from pathlib import Path

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401

pytestmark = pytest.mark.usefixtures("bridge_jar")

_SOURCE = "".join(
    "       " + line + "\n"
    for line in (
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. STAMPED.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-W PIC X(21).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        "    MOVE FUNCTION WHEN-COMPILED TO WS-W.",
        "    GOBACK.",
    )
).encode()


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_two_parses_of_one_program_write_the_same_asg(tmp_path: Path) -> None:
    parser = make_cobol_parser()
    first = parser.parse_to_file(_SOURCE, tmp_path / "first.json")
    second = parser.parse_to_file(_SOURCE, tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
