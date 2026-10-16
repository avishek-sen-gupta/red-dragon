"""Size error and ROUNDED on arithmetic receivers: what is stored, and when ON SIZE ERROR runs."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _display_after(
    capsys: pytest.CaptureFixture[str],
    working_storage: Sequence[str],
    procedure: Sequence[str],
    shown: Sequence[str],
) -> list[str]:
    run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SIZEERR.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "01 SEP PIC X VALUE '|'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            *[f"    DISPLAY {name} SEP." for name in shown],
            "    STOP RUN.",
        ],
        max_steps=5000,
    )
    return capsys.readouterr().out.split("|")[:-1]


class TestSizeErrorThreshold:
    @covers(
        CobolFeature.ADD,
        CobolFeature.MULTIPLY,
        CobolFeature.DIVIDE,
        CobolFeature.ON_SIZE_ERROR,
    )
    def test_only_a_result_reaching_the_integer_capacity_is_a_size_error(self, capsys):
        shown = _display_after(
            capsys,
            [
                "01 D PIC 99V9 VALUE 99.9.",
                "01 A PIC 99V9 VALUE 2.1.",
                "01 C PIC V999 VALUE 0.",
                "01 T PIC V9(12) VALUE .00001.",
                "01 U PIC 99V9 VALUE 99.9.",
                "01 S PIC S9V9 VALUE -9.9.",
                "01 F1 PIC X VALUE 'P'.",
                "01 F2 PIC X VALUE 'P'.",
                "01 F3 PIC X VALUE 'P'.",
                "01 F4 PIC X VALUE 'P'.",
                "01 F5 PIC X VALUE 'P'.",
            ],
            [
                "    MULTIPLY 1 BY D GIVING D",
                "        ON SIZE ERROR MOVE 'E' TO F1.",
                "    DIVIDE 10 INTO A GIVING C",
                "        ON SIZE ERROR MOVE 'E' TO F2.",
                "    MULTIPLY .00001 BY T",
                "        ON SIZE ERROR MOVE 'E' TO F3.",
                "    ADD .1 TO U",
                "        ON SIZE ERROR MOVE 'E' TO F4.",
                "    SUBTRACT .1 FROM S",
                "        ON SIZE ERROR MOVE 'E' TO F5.",
            ],
            ["D", "C", "T", "U", "S", "F1", "F2", "F3", "F4", "F5"],
        )
        assert shown == [
            "999",
            "210",
            "000000000100",
            "999",
            "-9.9",
            "P",
            "P",
            "P",
            "E",
            "E",
        ]


class TestUnsignedReceiver:
    @covers(CobolFeature.MULTIPLY, CobolFeature.DIVIDE, CobolFeature.ON_SIZE_ERROR)
    def test_a_negative_result_is_judged_by_its_magnitude_not_its_sign(self, capsys):
        shown = _display_after(
            capsys,
            [
                "01 M4 PIC S99 VALUE -56.",
                "01 M1 PIC 99V99 VALUE 80.12.",
                "01 U PIC 9 VALUE 4.",
                "01 A PIC 99V9 VALUE 44.1.",
                "01 B PIC S9V999 VALUE -9.642.",
                "01 C PIC V999 VALUE .111.",
                "01 W PIC 9 VALUE 4.",
                "01 X PIC V99 VALUE .11.",
                "01 F1 PIC X VALUE 'P'.",
                "01 F2 PIC X VALUE 'P'.",
                "01 F3 PIC X VALUE 'P'.",
                "01 F4 PIC X VALUE 'P'.",
            ],
            [
                "    MULTIPLY M4 BY M1 GIVING U",
                "        ON SIZE ERROR MOVE 'E' TO F1.",
                "    DIVIDE B INTO A GIVING C",
                "        ON SIZE ERROR MOVE 'E' TO F2.",
                "    MULTIPLY -3 BY 3 GIVING W",
                "        ON SIZE ERROR MOVE 'E' TO F3.",
                "    DIVIDE -9.9 INTO 1 GIVING X",
                "        ON SIZE ERROR MOVE 'E' TO F4.",
            ],
            ["U", "C", "W", "X", "F1", "F2", "F3", "F4"],
        )
        assert shown == ["4", "111", "9", "10", "E", "E", "P", "P"]


class TestRoundedSizeError:
    @covers(
        CobolFeature.MULTIPLY,
        CobolFeature.DIVIDE,
        CobolFeature.COMPUTE,
        CobolFeature.ROUNDED_CLAUSE,
        CobolFeature.ON_SIZE_ERROR,
    )
    def test_the_size_error_is_judged_on_the_rounded_value(self, capsys):
        shown = _display_after(
            capsys,
            [
                "01 S PIC S99 VALUE -1.",
                "01 T PIC S99 VALUE -1.",
                "01 G PIC 99 VALUE 7.",
                "01 C1 PIC 999 VALUE 0.",
                "01 C2 PIC 99 VALUE 7.",
                "01 C3 PIC 99 VALUE 7.",
                "01 F1 PIC X VALUE 'P'.",
                "01 F2 PIC X VALUE 'P'.",
                "01 F3 PIC X VALUE 'P'.",
                "01 F4 PIC X VALUE 'P'.",
                "01 F5 PIC X VALUE 'P'.",
            ],
            [
                "    MULTIPLY 99.4 BY S ROUNDED",
                "        ON SIZE ERROR MOVE 'E' TO F1.",
                "    MULTIPLY 99.5 BY T ROUNDED",
                "        ON SIZE ERROR MOVE 'E' TO F2.",
                "    DIVIDE 1.0051 INTO 100.50 GIVING G ROUNDED",
                "        ON SIZE ERROR MOVE 'E' TO F3.",
                "    COMPUTE C1 C2 ROUNDED = 99.6",
                "        ON SIZE ERROR MOVE 'E' TO F4.",
                "    COMPUTE C3 ROUNDED = 99.4",
                "        ON SIZE ERROR MOVE 'E' TO F5.",
            ],
            ["S", "T", "G", "C1", "C2", "C3", "F1", "F2", "F3", "F4", "F5"],
        )
        assert shown == [
            "-99",
            "-1",
            "07",
            "099",
            "07",
            "99",
            "P",
            "E",
            "E",
            "E",
            "P",
        ]
