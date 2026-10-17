"""An edited item's VALUE is its literal's characters; INITIALIZE edits a MOVE."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration import cobol_helpers
from tests.integration.cobol_helpers import first_region, run_cobol

bridge_jar = cobol_helpers.bridge_jar


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar: str) -> None:
    """Fail loudly when PROLEAP_BRIDGE_JAR is unset."""


def _chars(lines: Sequence[str], length: int) -> str:
    vm = run_cobol(list(lines), max_steps=20000)
    return bytes(first_region(vm)[0:length]).decode("cp037")


def _program(fields: Sequence[str], statements: Sequence[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. EDVAL.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 REC.",
        *fields,
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *statements,
        "    STOP RUN.",
    ]


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.VALUE_CLAUSE)
def test_numeric_edited_value_stores_a_nonnumeric_literal_and_edits_a_numeric_one(
    bridge_jar: str,
) -> None:
    fields = [
        '    05 E1 PIC $$$,$$$.99 VALUE " $1,111.11".',
        '    05 E2 PIC $(3)9.99 VALUE "  $1.50".',
        "    05 E3 PIC ZZ9.99 VALUE 12.5.",
        "    05 E4 PIC 9(3).99 VALUE 7.",
        '    05 E5 PIC ZZ9 VALUE "12".',
    ]
    obj = json.loads(
        RealSubprocessRunner().run(
            ["java", "-jar", bridge_jar],
            cobol_helpers.to_fixed(_program(fields, [])),
        )
    )
    numeric = {
        child["name"]: child.get("value_is_numeric", False)
        for child in obj["data_fields"][0]["children"]
    }
    assert (numeric, _chars(_program(fields, []), 32)) == (
        {"E1": False, "E2": False, "E3": True, "E4": True, "E5": False},
        " $1,111.11" "  $1.50" " 12.50" "007.00" "12 ",
    )


@covers(CobolFeature.INITIALIZE, CobolFeature.NUMERIC_EDITED)
def test_initialize_edits_zero_and_spaces_into_edited_items() -> None:
    fields = [
        '    05 N1 PIC $(3)9.99 VALUE "  $9.99".',
        '    05 N2 PIC ZZZ,ZZZ.99 VALUE "    123.45".',
        '    05 A1 PIC XXBXX/XX VALUE "AB CD/EF".',
        '    05 X1 PIC X(3) VALUE "ABC".',
        "    05 D1 PIC 9(3) VALUE 123.",
    ]
    assert _chars(_program(fields, ["    INITIALIZE REC."]), 31) == (
        "  $0.00" "       .00" "     /  " "   " "000"
    )


@covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.NUMERIC_EDITED)
def test_blank_when_zero_blanks_a_move_of_zero_but_not_a_value() -> None:
    fields = [
        "    05 M1 PIC $99,999.99 BLANK WHEN ZERO.",
        "    05 M2 PIC $9999 BLANK WHEN ZERO.",
        "    05 V1 PIC ZZ9.99 BLANK WHEN ZERO VALUE 0.",
        '    05 V2 PIC 999 VALUE "000" BLANK WHEN ZERO.',
        "    05 M3 PIC $9999 BLANK WHEN ZERO.",
    ]
    statements = ["    MOVE 0 TO M1.", "    MOVE 0 TO M2.", "    MOVE 12 TO M3."]
    assert _chars(_program(fields, statements), 29) == (
        "          " "     " "  0.00" "000" "$0012"
    )
