"""DECIMAL-POINT IS COMMA in numeric literals and pictures, and doubled quotes in nonnumeric literals, end to end."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_COMMA_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. DCOMMA.",
    "ENVIRONMENT DIVISION.",
    "CONFIGURATION SECTION.",
    "SPECIAL-NAMES.",
    "    DECIMAL-POINT IS COMMA.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-VALUED PIC 9(4)V99 VALUE 1234,56.",
    "01 WS-MOVED PIC 9(6)V99.",
    "01 WS-EDITED PIC 9.999.999,99.",
    "01 WS-FLAG PIC X VALUE 'N'.",
    "01 WS-RATE PIC 9V9 VALUE 2,5.",
    "    88 RATE-HALF-UP VALUE 2,5.",
    "01 WS-RATE-FLAG PIC X VALUE 'N'.",
    "01 WS-COMPUTED PIC 99V99.",
    "01 WS-TEXT PIC X(3) VALUE '1,5'.",
    "PROCEDURE DIVISION.",
    "    MOVE 1,5 TO WS-MOVED.",
    "    MOVE 1234567,89 TO WS-EDITED.",
    "    IF WS-MOVED = 1,5 MOVE 'Y' TO WS-FLAG.",
    "    IF RATE-HALF-UP MOVE 'Y' TO WS-RATE-FLAG.",
    "    COMPUTE WS-COMPUTED = WS-RATE * 2,25.",
    "    STOP RUN.",
]

_QUOTE_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. DQUOTE.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    '01 WS-VALUED PIC X(5) VALUE "A""B".',
    "01 WS-MOVED PIC X(5).",
    "01 WS-FLAG PIC X VALUE 'N'.",
    "PROCEDURE DIVISION.",
    '    MOVE "C""D" TO WS-MOVED.',
    '    IF WS-VALUED = "A""B  " MOVE \'Y\' TO WS-FLAG.',
    "    STOP RUN.",
]


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.VALUE_CLAUSE)
def test_the_comma_is_the_decimal_point_in_literals_and_pictures() -> None:
    ws = bytes(ws_region(run_cobol_programs(_COMMA_PROGRAM, {}), "DCOMMA"))

    assert ws.decode("cp037") == (
        "123456" + "00000150" + "1.234.567,89" + "Y" + "25" + "Y" + "0562" + "1,5"
    )


@covers(CobolFeature.VALUE_CLAUSE)
def test_a_doubled_quote_in_a_literal_is_one_quote() -> None:
    ws = bytes(ws_region(run_cobol_programs(_QUOTE_PROGRAM, {}), "DQUOTE"))

    assert ws.decode("cp037") == 'A"B  ' + 'C"D  ' + "Y"
