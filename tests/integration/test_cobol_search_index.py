"""End-to-end: SEARCH advances the table's own index, SEARCH ALL searches the whole
table, and both stop at the occurrence count OCCURS DEPENDING ON currently holds.

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
            "PROGRAM-ID. SRCHIX.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 RESULTS.",
            *[f"   05 R{n} PIC 99 VALUE 0." for n in range(count)],
            *storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *(f"    {line}" for line in procedure),
            "    STOP RUN.",
        ],
        max_steps=50000,
    )
    region = ws_region(vm, "SRCHIX")
    return [_decode(region, 2 * n, 2) for n in range(count)]


_TEN = [
    "01 TV.",
    "   05 FILLER PIC X(10) VALUE '0102030405'.",
    "   05 FILLER PIC X(10) VALUE '0607080910'.",
    "01 TA REDEFINES TV.",
    "   05 ELMT PIC 99 OCCURS 10 INDEXED BY A A2.",
    "01 TB.",
    "   05 OTHER-E PIC 99 OCCURS 10 INDEXED BY B.",
    "01 N PIC 99 VALUE 0.",
]


@pytest.mark.usefixtures("bridge_jar")
class TestSearchIndex:
    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_VARYING,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
    )
    def test_varying_steps_alongside_the_search_index(self):
        assert _results(
            _TEN,
            [
                "SET A TO 1. MOVE 1 TO N.",
                "SEARCH ELMT VARYING N AT END MOVE 99 TO R0",
                "    WHEN ELMT (A) = 5 MOVE 1 TO R0.",
                "SET R1 TO A. MOVE N TO R2.",
                "SET A TO 2. SET B TO 7.",
                "SEARCH ELMT VARYING B AT END MOVE 99 TO R3",
                "    WHEN ELMT (A) = 4 MOVE 1 TO R3.",
                "SET R4 TO A. SET R5 TO B.",
                "SET A TO 1. SET A2 TO 3.",
                "SEARCH ELMT VARYING A2 AT END MOVE 99 TO R6",
                "    WHEN ELMT (A2) = 6 MOVE 1 TO R6.",
                "SET R7 TO A2. SET R8 TO A.",
                "SET A TO 1. MOVE 1 TO N.",
                "SEARCH ELMT VARYING N AT END MOVE 99 TO R9",
                "    WHEN ELMT (A) = 11 MOVE 1 TO R9.",
            ],
            10,
        ) == [1, 5, 5, 1, 4, 9, 1, 6, 1, 99]

    @covers(
        CobolFeature.SEARCH_BINARY,
        CobolFeature.SEARCH_AT_END,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
    )
    def test_search_all_searches_the_whole_table_whatever_the_index_holds(self):
        assert _results(
            [
                "01 KV PIC X(8) VALUE '02040608'.",
                "01 KT REDEFINES KV.",
                "   05 E OCCURS 4 ASCENDING KEY IS K INDEXED BY I.",
                "      10 K PIC 99.",
            ],
            [
                "SET I TO 3.",
                "SEARCH ALL E AT END MOVE 99 TO R0",
                "    WHEN K (I) = 4 MOVE 1 TO R0.",
                "SET R1 TO I.",
                "SEARCH ALL E AT END MOVE 99 TO R2",
                "    WHEN K (I) = 8 MOVE 1 TO R2.",
                "SET R3 TO I.",
                "SEARCH ALL E AT END MOVE 99 TO R4",
                "    WHEN K (I) = 5 MOVE 1 TO R4.",
            ],
            5,
        ) == [1, 2, 1, 4, 99]

    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_BINARY,
        CobolFeature.SEARCH_AT_END,
    )
    def test_occurs_depending_on_bounds_both_searches(self):
        assert _results(
            [
                "01 LEN PIC 99 VALUE 6.",
                "01 TBL.",
                "   05 ENT OCCURS 1 TO 6 DEPENDING ON LEN",
                "         ASCENDING KEY IS KY INDEXED BY I1.",
                "      10 KY PIC 99.",
            ],
            [
                "MOVE 10 TO KY (1). MOVE 20 TO KY (2). MOVE 30 TO KY (3).",
                "MOVE 40 TO KY (4). MOVE 50 TO KY (5). MOVE 60 TO KY (6).",
                "MOVE 4 TO LEN.",
                "SET I1 TO 1.",
                "SEARCH ENT AT END MOVE 99 TO R0",
                "    WHEN KY (I1) = 50 MOVE 1 TO R0.",
                "SEARCH ALL ENT AT END MOVE 99 TO R1",
                "    WHEN KY (I1) = 50 MOVE 1 TO R1.",
                "MOVE 6 TO LEN.",
                "SET I1 TO 1.",
                "SEARCH ENT AT END MOVE 99 TO R2",
                "    WHEN KY (I1) = 50 MOVE 1 TO R2.",
                "SET R3 TO I1.",
                "SEARCH ALL ENT AT END MOVE 99 TO R4",
                "    WHEN KY (I1) = 40 MOVE 1 TO R4.",
                "SET R5 TO I1.",
            ],
            6,
        ) == [99, 99, 1, 5, 1, 4]
