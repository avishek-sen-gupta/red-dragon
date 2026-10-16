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
                "    MOVE N TO R2. MOVE I TO R3. MOVE 0 TO N.",
                "    PERFORM BUMP WITH TEST AFTER",
                "        VARYING I FROM ONE BY STP UNTIL I > 4",
                "        AFTER J FROM STP BY STP3 UNTIL J > 7.",
                "    MOVE N TO R4.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
            ],
            5,
        ) == [4, 8, 4, 5, 4]

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
                "    MOVE N TO R3. MOVE 0 TO N.",
                "    PERFORM BUMP WITH TEST AFTER",
                "        VARYING EL (S1) FROM EL (1) BY EL (3)",
                "        UNTIL EL (S1) > 50.",
                "    MOVE N TO R4. MOVE EL (2) TO R5.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
            ],
            6,
        ) == [3, 80, 20, 4, 2, 60]
