"""A VALUE on an item that has or is subordinate to OCCURS initialises every
occurrence, at every level of the table."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OCCVAL.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-LEAF.",
    "   03 WS-E1 PIC XX OCCURS 3 VALUE 'AZ'.",
    "01 WS-ROWS.",
    "   03 WS-ROW OCCURS 2.",
    "      05 WS-E2 PIC XX VALUE 'BY'.",
    "      05 WS-N2 PIC 99 VALUE 7.",
    "01 WS-GRID.",
    "   03 WS-LINE OCCURS 2.",
    "      05 WS-CELL PIC X OCCURS 3 VALUE 'Q'.",
    "01 WS-PAIRS.",
    "   03 WS-PAIR OCCURS 2 VALUE 'MN'.",
    "      05 WS-M PIC X.",
    "      05 WS-N PIC X.",
    "PROCEDURE DIVISION.",
    "    STOP RUN.",
]


@covers(CobolFeature.VALUE_CLAUSE, CobolFeature.OCCURS_FIXED)
def test_a_value_under_occurs_initialises_every_occurrence() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "OCCVAL"))

    assert ws[:24].decode("cp037") == "AZAZAZBY07BY07QQQQQQMNMN"
