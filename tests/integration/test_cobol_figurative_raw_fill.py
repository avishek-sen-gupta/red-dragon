"""MOVE HIGH-VALUES / LOW-VALUES fills every receiver with the raw byte 0xFF /
0x00, whatever its category: a numeric, packed or binary receiver takes the
bytes as they are, not a number converted from them."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RAWFIL.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-ZONED  PIC 9(2) VALUE 12.",
    "01 WS-PACKED PIC S9(3) COMP-3 VALUE 5.",
    "01 WS-BINARY PIC S9(4) COMP VALUE 7.",
    "01 WS-CHARS  PIC X(2).",
    "01 WS-LOW    PIC 9(2) VALUE 56.",
    "PROCEDURE DIVISION.",
    "    MOVE HIGH-VALUES TO WS-ZONED WS-PACKED WS-BINARY WS-CHARS.",
    "    MOVE LOW-VALUES TO WS-LOW.",
    "    STOP RUN.",
]


@covers(CobolFeature.FIGURATIVE_HIGH_VALUES)
def test_high_and_low_values_fill_any_receiver_with_the_raw_byte() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "RAWFIL"))

    assert ws[:10] == bytes.fromhex("FFFF" "FFFF" "FFFF" "FFFF" "0000")
