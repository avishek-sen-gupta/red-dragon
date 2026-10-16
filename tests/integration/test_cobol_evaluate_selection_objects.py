"""End-to-end: EVALUATE compares each selection subject with its selection object.

Each EVALUATE writes M into its result character when a WHEN arm is selected and
O when WHEN OTHER is, so the assertions read the whole row of outcomes at once."""

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
    ws_region,
)


def _outcomes(procedure: Sequence[str], count: int) -> str:
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EVALSO.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            f"01 R PIC X({count}) VALUE SPACES.",
            "01 RT REDEFINES R.",
            f"   05 RC PIC X OCCURS {count}.",
            "01 X1 PIC X VALUE SPACE.",
            "01 X2 PIC X VALUE SPACE.",
            "01 X3 PIC X VALUE SPACE.",
            "01 D8 PIC 99 VALUE 0.",
            "01 FLAG PIC X VALUE 'Y'.",
            "   88 FLAG-ON VALUE 'Y'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *(f"    {line}" for line in procedure),
            "    STOP RUN.",
        ],
        max_steps=20000,
    )
    return ws_region(vm, "EVALSO")[:count].decode("cp037")


def _evaluate(position: int, head: str, *whens: str) -> list[str]:
    return [
        head,
        *(f"    WHEN {when} MOVE 'M' TO RC ({position})" for when in whens),
        f"    WHEN OTHER MOVE 'O' TO RC ({position})",
        "END-EVALUATE.",
    ]


@pytest.mark.usefixtures("bridge_jar")
class TestEvaluateSelectionObjects:
    @covers(CobolFeature.EVALUATE, CobolFeature.EVALUATE_WHEN_THRU)
    def test_not_negates_the_value_or_range_it_precedes(self):
        assert (
            _outcomes(
                [
                    "MOVE '6' TO X1. MOVE '6' TO X2.",
                    *_evaluate(1, "EVALUATE X1", "NOT X2"),
                    "MOVE '1' TO X1. MOVE '*' TO X2.",
                    *_evaluate(2, "EVALUATE X1", "NOT X2"),
                    "MOVE 'A' TO X1.",
                    *_evaluate(3, "EVALUATE X1", "NOT 'A'"),
                    *_evaluate(4, "EVALUATE X1", "NOT 'Z'"),
                    "MOVE '5' TO X1. MOVE '1' TO X2. MOVE '9' TO X3.",
                    *_evaluate(5, "EVALUATE X1", "NOT X2 THRU X3"),
                    "MOVE 'A' TO X1.",
                    *_evaluate(6, "EVALUATE X1", "NOT X2 THROUGH X3"),
                    "MOVE 26 TO D8.",
                    *_evaluate(7, "EVALUATE 26", "NOT D8"),
                    *_evaluate(8, "EVALUATE X1 ALSO D8", "'A' ALSO NOT 26"),
                    *_evaluate(9, "EVALUATE X1 ALSO D8", "'A' ALSO NOT 1 THRU 9"),
                ],
                9,
            )
            == "OMOMOMOOM"
        )

    @covers(CobolFeature.EVALUATE)
    def test_a_condition_or_truth_value_subject_selects_by_truth_value(self):
        assert (
            _outcomes(
                [
                    "MOVE '6' TO X1.",
                    *_evaluate(1, "EVALUATE X1 NUMERIC", "TRUE"),
                    *_evaluate(2, "EVALUATE X1 NUMERIC", "FALSE"),
                    "MOVE '*' TO X1.",
                    *_evaluate(3, "EVALUATE X1 NOT NUMERIC", "TRUE"),
                    *_evaluate(4, "EVALUATE FALSE", "X1 = SPACE"),
                    "MOVE SPACE TO X1.",
                    *_evaluate(5, "EVALUATE FALSE", "X1 = SPACE"),
                    *_evaluate(6, "EVALUATE TRUE", "X1 = SPACE"),
                    "MOVE 7 TO D8.",
                    *_evaluate(7, "EVALUATE TRUE ALSO FALSE", "D8 > 5 ALSO D8 = 0"),
                    *_evaluate(8, "EVALUATE X1 = SPACE", "D8 > 5"),
                    *_evaluate(9, "EVALUATE X1 = SPACE", "D8 < 5"),
                    *_evaluate(10, "EVALUATE TRUE", "FLAG-ON"),
                    *_evaluate(11, "EVALUATE FALSE", "FLAG-ON"),
                    *_evaluate(12, "EVALUATE TRUE", "NOT FLAG-ON"),
                    *_evaluate(13, "EVALUATE FLAG-ON", "FALSE"),
                    *_evaluate(14, "EVALUATE FLAG-ON ALSO D8", "TRUE ALSO 7"),
                ],
                14,
            )
            == "MOMMOMMMOMOOOM"
        )

    @covers(CobolFeature.EVALUATE, CobolFeature.EVALUATE_WHEN_THRU)
    def test_arithmetic_expressions_are_evaluated_as_subject_value_and_bound(self):
        assert (
            _outcomes(
                [
                    "MOVE 89 TO D8.",
                    *_evaluate(1, "EVALUATE D8", "(33 + (99 - 43))"),
                    "MOVE 9 TO D8.",
                    *_evaluate(2, "EVALUATE (D8 * 9)", "81"),
                    "MOVE 50 TO D8.",
                    *_evaluate(3, "EVALUATE D8", "(11 + (99 - 20)) THRU (20 * 5)"),
                    "MOVE 95 TO D8.",
                    *_evaluate(4, "EVALUATE D8", "(11 + (99 - 20)) THRU (20 * 5)"),
                    *_evaluate(5, "EVALUATE (D8 - 90) ALSO D8", "5 ALSO (D8 + 0)"),
                ],
                5,
            )
            == "MMOMM"
        )
