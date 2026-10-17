"""IS NUMERIC on a numeric item tests its stored bytes, end to end."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. NUMCLASS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 XN PIC X(18) VALUE '00ABCDEFGHI  4321 '.",
    "01 ND REDEFINES XN PIC S9(18).",
    "01 X4 PIC X(4) VALUE '12AB'.",
    "01 U4 REDEFINES X4 PIC 9(4).",
    "01 GOOD PIC S9(3) VALUE -12.",
    "01 PX PIC X(3) VALUE X'12345C'.",
    "01 PK REDEFINES PX PIC 9(5) COMP-3.",
    "01 SPK PIC S9(5) COMP-3 VALUE -123.",
    "01 FLAGS PIC X(6) VALUE ALL 'N'.",
    "PROCEDURE DIVISION.",
    "    IF ND IS NUMERIC MOVE 'Y' TO FLAGS(1:1).",
    "    IF ND IS NOT NUMERIC MOVE 'Y' TO FLAGS(2:1).",
    "    IF U4 IS NUMERIC MOVE 'Y' TO FLAGS(3:1).",
    "    IF GOOD IS NUMERIC MOVE 'Y' TO FLAGS(4:1).",
    "    IF PK IS NUMERIC MOVE 'Y' TO FLAGS(5:1).",
    "    IF SPK IS NUMERIC MOVE 'Y' TO FLAGS(6:1).",
    "    STOP RUN.",
]


@covers(CobolFeature.CLASS_CONDITION)
def test_is_numeric_reads_the_stored_digits_and_sign() -> None:
    """ANSI X3.23-1985 / IBM Enterprise COBOL LR class condition: an item
    described as numeric is NUMERIC when its stored characters are digits, with
    a valid operational sign when the picture is signed and none when it is
    not. An unsigned packed item holding a C sign is therefore NOT NUMERIC."""
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "NUMCLASS"))

    assert ws[-6:].decode("cp037") == "NYNYNY"
