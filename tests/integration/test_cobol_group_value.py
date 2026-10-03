"""A VALUE on a group item initialises the group's whole storage as
alphanumeric: a literal padded with spaces, a figurative constant repeated,
whatever the subordinate items' own types or OCCURS."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. GRPVAL.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-TAB VALUE '123'.",
    "   05 WS-T PIC 9 OCCURS 3.",
    "01 WS-PAIR VALUE 'AB'.",
    "   05 WS-P1 PIC X(2).",
    "   05 WS-P2 PIC X(2).",
    "01 WS-ZERO VALUE ZEROS.",
    "   05 WS-Z PIC X(3).",
    "01 WS-HIGH VALUE HIGH-VALUES.",
    "   05 WS-H PIC X(2).",
    "PROCEDURE DIVISION.",
    "    STOP RUN.",
]


@covers(CobolFeature.VALUE_CLAUSE)
def test_a_group_value_initialises_the_whole_group() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "GRPVAL"))

    assert (ws[:10].decode("cp037"), ws[10:12]) == ("123AB  000", b"\xff\xff")
