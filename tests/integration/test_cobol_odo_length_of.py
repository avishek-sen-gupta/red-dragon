"""LENGTH OF and FUNCTION LENGTH of an item ending in an OCCURS DEPENDING ON
table follow the object's current value."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ODOLOF.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 N  PIC 9    VALUE 3.",
    "01 L1 PIC 99   VALUE 0.",
    "01 L2 PIC 99   VALUE 0.",
    "01 L3 PIC 99   VALUE 0.",
    "01 L4 PIC 99   VALUE 0.",
    "01 W  PIC X(16) VALUE ALL 'W'.",
    "01 G.",
    "   02 H PIC X(2) VALUE 'HH'.",
    "   02 T PIC X(4) OCCURS 1 TO 5 TIMES DEPENDING ON N.",
    "PROCEDURE DIVISION.",
    "    MOVE LENGTH OF G TO L1",
    "    COMPUTE L2 = LENGTH OF G + 1",
    "    MOVE FUNCTION LENGTH(G) TO L3",
    "    MOVE 'Z' TO W(LENGTH OF G:1)",
    "    MOVE 5 TO N",
    "    MOVE LENGTH OF G TO L4",
    "    STOP RUN.",
]


@covers(CobolFeature.OCCURS_DEPENDING_ON, CobolFeature.MOVE)
def test_length_of_an_odo_group_is_its_current_length() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "ODOLOF"))

    assert ws[:25].decode("cp037") == ("5" "14" "15" "14" "22" "WWWWWWWWWWWWWZWW")
