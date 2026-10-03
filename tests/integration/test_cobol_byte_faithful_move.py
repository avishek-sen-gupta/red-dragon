"""An alphanumeric MOVE copies every byte as it is -- the upper half of the
code page and control bytes included -- and a field holding HIGH-VALUE
compares equal to HIGH-VALUE."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. BYTMOV.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-SRC  PIC X(4) VALUE X'FF4AB106'.",
    "01 WS-DST  PIC X(4).",
    "01 WS-GRP.",
    "   05 WS-GX PIC X(4).",
    "01 WS-H    PIC X(1).",
    "01 WS-HIT  PIC X(1) VALUE 'N'.",
    "PROCEDURE DIVISION.",
    "    MOVE WS-SRC TO WS-DST.",
    "    MOVE WS-DST TO WS-GRP.",
    "    MOVE HIGH-VALUE TO WS-H.",
    "    IF WS-H = HIGH-VALUE MOVE 'Y' TO WS-HIT.",
    "    STOP RUN.",
]


@covers(CobolFeature.FIGURATIVE_HIGH_VALUES)
def test_an_alphanumeric_move_copies_every_byte_unchanged() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "BYTMOV"))

    assert ws[:14] == bytes.fromhex("FF4AB106" "FF4AB106" "FF4AB106" "FF" "E8")
