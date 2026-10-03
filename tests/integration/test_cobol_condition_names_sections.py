"""A level-88 condition name resolves whichever section declares its parent:
LINKAGE, LOCAL-STORAGE and the FILE SECTION as well as WORKING-STORAGE, both
when tested and when SET TO TRUE -- and SET on a LINKAGE item writes the
caller's byte."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CNMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 FLAG PIC X VALUE 'Y'.",
    "PROCEDURE DIVISION.",
    "    CALL 'CNSUB' USING FLAG.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CNSUB.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT CN-FILE ASSIGN TO CNFILE.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD CN-FILE.",
    "01 FD-REC.",
    "   05 FD-KIND PIC X.",
    "      88 FD-HEADER VALUE 'H'.",
    "WORKING-STORAGE SECTION.",
    "01 WS-SEEN PIC X(3) VALUE '---'.",
    "LOCAL-STORAGE SECTION.",
    "01 LS-STATE PIC X VALUE 'A'.",
    "   88 LS-ACTIVE VALUE 'A'.",
    "   88 LS-DONE VALUE 'D'.",
    "LINKAGE SECTION.",
    "01 LK-FLAG PIC X.",
    "   88 LK-ON VALUE 'Y'.",
    "   88 LK-OFF VALUE 'N'.",
    "PROCEDURE DIVISION USING LK-FLAG.",
    "    IF LK-ON MOVE 'L' TO WS-SEEN(1:1).",
    "    IF LS-ACTIVE MOVE 'S' TO WS-SEEN(2:1).",
    "    SET FD-HEADER TO TRUE.",
    "    IF FD-HEADER MOVE 'F' TO WS-SEEN(3:1).",
    "    SET LK-OFF TO TRUE.",
    "    GOBACK.",
]


@covers(CobolFeature.LEVEL_88_CONDITION)
def test_a_condition_name_resolves_in_every_section() -> None:
    vm = run_cobol_programs(_MAIN, {"CNSUB": _SUB})

    assert (
        bytes(ws_region(vm, "CNSUB"))[:3].decode("cp037"),
        bytes(ws_region(vm, "CNMAIN"))[:1].decode("cp037"),
    ) == ("LSF", "N")
