"""End-to-end: SET, PERFORM TIMES and relation conditions address the occurrence
a subscripted operand selects.

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
            "PROGRAM-ID. SUBOPS.",
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
    region = ws_region(vm, "SUBOPS")
    return [_decode(region, 2 * n, 2) for n in range(count)]


@pytest.mark.usefixtures("bridge_jar")
class TestSubscriptedOperands:
    @covers(
        CobolFeature.SET_TO,
        CobolFeature.SET_UP_BY,
        CobolFeature.SET_DOWN_BY,
        CobolFeature.OCCURS_FIXED,
    )
    def test_set_targets_and_values_address_their_occurrence(self):
        assert _results(
            [
                "01 W PIC 99 VALUE 5.",
                "01 TB.",
                "   02 G OCCURS 5 INDEXED BY I1 I3.",
                "      03 E1 PIC 99.",
                "01 TR-T.",
                "   02 TR PIC 99 OCCURS 12 INDEXED BY I2 IX.",
            ],
            [
                "MAIN-PARA.",
                "    MOVE 0 TO E1 (1) E1 (2) E1 (3) E1 (4) E1 (5).",
                "    MOVE 21 TO TR (1). MOVE 2 TO TR (6). MOVE 4 TO TR (12).",
                "    SET I1 TO 3. SET I3 TO 4.",
                "    SET E1 (2) TO I1. SET E1 (3) TO I3.",
                "    SET E1 (1) TO I1. SET E1 (4) TO I3. SET E1 (W) TO I3.",
                "    MOVE E1 (1) TO R0. MOVE E1 (2) TO R1. MOVE E1 (3) TO R2.",
                "    MOVE E1 (4) TO R3. MOVE E1 (5) TO R4.",
                "    SET IX TO TR (12). SET R5 TO IX.",
                "    SET I2 TO 2. SET IX UP BY TR (I2 + 4). SET R6 TO IX.",
                "    SET IX DOWN BY TR (12). SET R7 TO IX.",
                "    STOP RUN.",
            ],
            8,
        ) == [3, 3, 4, 4, 4, 4, 6, 2]

    @covers(CobolFeature.PERFORM_TIMES, CobolFeature.OCCURS_FIXED)
    def test_perform_times_counts_the_subscripted_occurrence(self):
        assert _results(
            [
                "01 S1 PIC 9 VALUE 3.",
                "01 TB.",
                "   02 T5 PIC 9 OCCURS 3 INDEXED BY IX5.",
            ],
            [
                "MAIN-PARA.",
                "    MOVE 1 TO T5 (1). MOVE 4 TO T5 (2). MOVE 2 TO T5 (3).",
                "    SET IX5 TO 2.",
                "    PERFORM BUMP T5 (IX5) TIMES.",
                "    MOVE N TO R0. MOVE 0 TO N.",
                "    PERFORM BUMP T5 (S1) TIMES.",
                "    MOVE N TO R1. MOVE 0 TO N.",
                "    PERFORM BUMP S1 TIMES.",
                "    MOVE N TO R2. MOVE 0 TO N.",
                "    PERFORM BUMP 5 TIMES.",
                "    MOVE N TO R3.",
                "    STOP RUN.",
                "BUMP.",
                "    ADD 1 TO N.",
            ],
            4,
        ) == [4, 2, 3, 5]

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.OCCURS_FIXED)
    def test_literal_compared_with_an_occurrence_is_sized_to_the_occurrence(self):
        assert _results(
            [
                "01 TB.",
                "   02 E1 PIC 9 OCCURS 4.",
                "01 RDS PIC X(4) VALUE '1 34'.",
                "01 RTS REDEFINES RDS.",
                "   02 EB PIC X OCCURS 4.",
            ],
            [
                "MAIN-PARA.",
                "    MOVE 6 TO E1 (1).",
                "    IF E1 (1) EQUAL TO '6' MOVE 1 TO R0.",
                "    IF EB (1) NOT EQUAL '1' MOVE 9 TO R1 ELSE MOVE 1 TO R1.",
                "    IF EB (2) EQUAL SPACE MOVE 1 TO R2.",
                "    STOP RUN.",
            ],
            3,
        ) == [1, 1, 1]

    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.OCCURS_FIXED)
    def test_set_condition_name_to_true_sets_the_subscripted_occurrence(self):
        assert _results(
            [
                "01 S PIC 9 VALUE 3.",
                "01 TB.",
                "   02 E PIC 99 OCCURS 3.",
                "      88 HIT VALUE 42.",
                "01 TU.",
                "   02 G OCCURS 2.",
                "      03 F PIC 99 OCCURS 2.",
                "         88 F-HIT VALUE 7.",
            ],
            [
                "MAIN-PARA.",
                "    MOVE 0 TO E (1) E (2) E (3).",
                "    MOVE 0 TO F (1, 1) F (1, 2) F (2, 1) F (2, 2).",
                "    SET HIT (2) TO TRUE. SET HIT (S) TO TRUE.",
                "    SET F-HIT (2, 1) TO TRUE.",
                "    MOVE E (1) TO R0. MOVE E (2) TO R1. MOVE E (3) TO R2.",
                "    MOVE F (1, 1) TO R3. MOVE F (1, 2) TO R4.",
                "    MOVE F (2, 1) TO R5. MOVE F (2, 2) TO R6.",
                "    STOP RUN.",
            ],
            7,
        ) == [0, 42, 42, 0, 0, 7, 0]
