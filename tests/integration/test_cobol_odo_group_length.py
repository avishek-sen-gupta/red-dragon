"""Integration: a group holding an OCCURS DEPENDING ON table is as long as its object says."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(
    CobolFeature.OCCURS_DEPENDING_ON, CobolFeature.MOVE, CobolFeature.INSPECT_TALLYING
)
def test_odo_group_length_follows_the_object_for_senders_and_outside_object_receivers():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ODOLEN.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 R-MOVE   PIC X(8).",
            "01 R-EQ     PIC X.",
            "01 R-TALLY  PIC 9.",
            "01 R-STR    PIC X(8).",
            "01 R-IN     PIC X(6).",
            "01 R-OUT    PIC X(6).",
            "01 R-UNS    PIC X(6).",
            "01 GRP.",
            "   02 CNT   PIC 9.",
            "   02 HDR   PIC XX.",
            "   02 TBL.",
            "      03 ELT PIC X OCCURS 0 TO 3 TIMES DEPENDING ON CNT.",
            "01 IN-GRP.",
            "   02 IN-CNT PIC 9.",
            "   02 IN-ELT PIC X OCCURS 0 TO 5 TIMES DEPENDING ON IN-CNT.",
            "01 OUT-CNT  PIC 9.",
            "01 OUT-GRP.",
            "   02 OUT-ELT PIC X OCCURS 0 TO 6 TIMES DEPENDING ON OUT-CNT.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE 3 TO CNT",
            "    MOVE 'HD' TO HDR",
            "    MOVE 'XYZ' TO TBL",
            "    MOVE 1 TO CNT",
            "    MOVE GRP TO R-MOVE",
            "    MOVE 'N' TO R-EQ",
            "    IF GRP = '1HDX' MOVE 'Y' TO R-EQ END-IF",
            "    MOVE 0 TO R-TALLY",
            "    INSPECT TBL TALLYING R-TALLY FOR ALL 'Z'",
            "    MOVE SPACES TO R-STR",
            "    STRING GRP '-' DELIMITED BY SIZE INTO R-STR",
            "    MOVE 5 TO IN-CNT",
            "    MOVE 'ABCDE' TO IN-ELT (1) IN-ELT (2) IN-ELT (3)",
            "    MOVE 2 TO IN-CNT",
            "    MOVE '4PQRST' TO IN-GRP",
            "    MOVE IN-GRP TO R-IN",
            "    MOVE 6 TO OUT-CNT",
            "    MOVE 'ABCDEF' TO OUT-GRP",
            "    MOVE 2 TO OUT-CNT",
            "    MOVE 'XYZ' TO OUT-GRP",
            "    MOVE 6 TO OUT-CNT",
            "    MOVE OUT-GRP TO R-OUT",
            "    MOVE 2 TO OUT-CNT",
            "    UNSTRING OUT-GRP DELIMITED BY 'D' INTO R-UNS",
            "    STOP RUN.",
        ],
        max_steps=200_000,
    )
    assert bytes(first_region(vm)[:36]).decode("cp037") == (
        "1HDX    " "Y" "0" "1HDX-   " "4PQRS " "XYCDEF" "XY    "
    )
