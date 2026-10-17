"""DIVIDE ... REMAINDER: the remainder is taken from the quotient as its receiver holds it."""

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
            "PROGRAM-ID. DIVREM.",
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


class TestDivideRemainder:
    @covers(
        CobolFeature.DIVIDE,
        CobolFeature.GIVING_CLAUSE,
        CobolFeature.DIVIDE_REMAINDER,
        CobolFeature.ROUNDED_CLAUSE,
    )
    def test_the_remainder_uses_the_quotient_truncated_to_its_receiver(self, capsys):
        shown = _display_after(
            capsys,
            [
                "01 Q1 PIC 9(4)V9 VALUE 0.",
                "01 R1 PIC 9(4)V9 VALUE 0.",
                "01 Q2 PIC 9V9(5) VALUE 0.",
                "01 R2 PIC 9V9(17) VALUE 0.",
                "01 Q3 PIC 9V9 VALUE 0.",
                "01 R3 PIC 9V9 VALUE 9.",
                "01 Q4 PIC 99 VALUE 0.",
                "01 R4 PIC 99 VALUE 0.",
            ],
            [
                "    DIVIDE 16 INTO 174 GIVING Q1 REMAINDER R1.",
                "    DIVIDE 10.0 INTO 3.14159265358979323",
                "        GIVING Q2 ROUNDED REMAINDER R2.",
                "    DIVIDE 7 BY 2 GIVING Q3 REMAINDER R3.",
                "    DIVIDE 100 BY 7 GIVING Q4 REMAINDER R4.",
            ],
            ["Q1", "R1", "Q2", "R2", "Q3", "R3", "Q4", "R4"],
        )
        assert shown == [
            "00108",
            "00012",
            "031416",
            "000009265358979323",
            "35",
            "00",
            "14",
            "02",
        ]
