"""End-to-end: PERFORM VARYING evaluates each of its operands as a data reference.

Every result is copied into the zoned two-digit fields at the start of
WORKING-STORAGE, so the assertions read them straight off the region."""

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
    ws_region,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)


def _results(storage: Sequence[str], procedure: Sequence[str], count: int) -> list[int]:
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. PVARY.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 RESULTS.",
            *[f"   05 R{n} PIC 99 VALUE 0." for n in range(count)],
            "01 N PIC 99 VALUE 0.",
            *storage,
            "PROCEDURE DIVISION.",
            *procedure,
        ],
        max_steps=20000,
    )
    region = ws_region(vm, "PVARY")
    return [_decode(region, 2 * n, 2) for n in range(count)]


@pytest.mark.usefixtures("bridge_jar")
class TestPerformVaryingOperands:
    @covers(CobolFeature.PERFORM_VARYING, CobolFeature.PERFORM_VARYING_AFTER)
    def test_identifier_from_and_by_step_by_the_identifiers_values(self):
        assert _results(
            [
                "01 I PIC 99 VALUE 0.",
                "01 J PIC 99 VALUE 0.",
                "01 ONE PIC 9 VALUE 1.",
                "01 STP PIC 9 VALUE 2.",
                "01 STP3 PIC 9 VALUE 3.",
            ],
            [
                "MAIN-PARA.",
                "    PERFORM BUMP VARYING I FROM 0 BY STP UNTIL I > 6.",
                "    MOVE N TO R0. MOVE I TO R1. MOVE 0 TO N.",
                "    PERFORM BUMP VARYING I FROM ONE BY STP UNTIL I > 4",
                "        AFTER J FROM STP BY STP3 UNTIL J > 7.",
                "    MOVE N TO R2. MOVE I TO R3. MOVE J TO R4. MOVE 0 TO N.",
                "    PERFORM BUMP WITH TEST AFTER",
                "        VARYING I FROM ONE BY STP UNTIL I > 4",
                "        AFTER J FROM STP BY STP3 UNTIL J > 7.",
                "    MOVE N TO R5.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
            ],
            6,
        ) == [4, 8, 4, 5, 2, 9]

    @covers(
        CobolFeature.PERFORM_VARYING,
        CobolFeature.PERFORM_VARYING_AFTER,
        CobolFeature.OCCURS_FIXED,
    )
    def test_subscripted_operands_address_their_occurrence(self):
        assert _results(
            [
                "01 I PIC 99 VALUE 0.",
                "01 S1 PIC 99 VALUE 2.",
                "01 TB.",
                "   03 EL PIC S9(3) COMP OCCURS 10.",
            ],
            [
                "MAIN-PARA.",
                "    MOVE 20 TO EL (1). MOVE 20 TO EL (3). MOVE 0 TO EL (2).",
                "    PERFORM BUMP VARYING EL (S1) FROM EL (1) BY EL (S1 + 1)",
                "        UNTIL EL (S1) > 70.",
                "    MOVE N TO R0. MOVE EL (2) TO R1. MOVE EL (1) TO R2.",
                "    MOVE 0 TO N.",
                "    PERFORM BUMP VARYING I FROM 1 BY 1 UNTIL I > 2",
                "        AFTER EL (S1) FROM 1 BY EL (3) UNTIL EL (S1) > 30.",
                "    MOVE N TO R3. MOVE EL (2) TO R4. MOVE 0 TO N.",
                "    PERFORM BUMP WITH TEST AFTER",
                "        VARYING EL (S1) FROM EL (1) BY EL (3)",
                "        UNTIL EL (S1) > 50.",
                "    MOVE N TO R5. MOVE EL (2) TO R6.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
            ],
            7,
        ) == [3, 80, 20, 4, 1, 3, 60]

    @covers(
        CobolFeature.PERFORM_VARYING,
        CobolFeature.PERFORM_VARYING_AFTER,
        CobolFeature.PERFORM_TEST_AFTER,
    )
    def test_outer_step_resets_inner_and_test_after_tests_before_stepping(self):
        assert _results(
            [
                "01 A1 PIC 99 VALUE 0.",
                "01 B1 PIC 99 VALUE 0.",
            ],
            [
                "MAIN-PARA.",
                "    PERFORM BUMP VARYING A1 FROM 1 BY 1 UNTIL A1 > 3",
                "        AFTER B1 FROM A1 BY 1 UNTIL B1 > 3.",
                "    MOVE N TO R0. MOVE A1 TO R1. MOVE B1 TO R2. MOVE 0 TO N.",
                "    PERFORM BUMP WITH TEST AFTER",
                "        VARYING A1 FROM 1 BY 1 UNTIL A1 > 3.",
                "    MOVE N TO R3. MOVE A1 TO R4. MOVE 0 TO N.",
                "    PERFORM SATISFY WITH TEST AFTER",
                "        VARYING A1 FROM 2 BY 5 UNTIL A1 = 1",
                "        AFTER B1 FROM 2 BY 6 UNTIL B1 > 19.",
                "    MOVE N TO R5. MOVE A1 TO R6. MOVE B1 TO R7.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
                "SATISFY.",
                "    ADD 1 TO N. MOVE 1 TO A1. MOVE 99 TO B1.",
            ],
            8,
        ) == [6, 4, 4, 4, 4, 1, 1, 99]
