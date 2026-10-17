"""A group sender moves its characters into an elementary receiver of any category, without conversion or editing."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. GRPMOVE.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 SENDER.",
    "   02 SENDER-DIGITS PIC 999 VALUE 123.",
    "   02 SENDER-LETTERS PIC AAA VALUE 'ABC'.",
    "01 DIGITS-GROUP.",
    "   02 TEN-DIGITS PIC 9(10) VALUE 0123456789.",
    "01 R-NUMERIC PIC 99.",
    "01 R-SCALED PIC 9999V999.",
    "01 R-AN-EDITED PIC 0XXXXX0.",
    "01 R-NUM-EDITED PIC ZZZ,999.999,9.",
    "01 R-ALPHA PIC X(8).",
    "PROCEDURE DIVISION.",
    "    MOVE SENDER TO R-NUMERIC R-SCALED R-AN-EDITED R-ALPHA.",
    "    MOVE DIGITS-GROUP TO R-NUM-EDITED.",
    "    STOP RUN.",
]


@covers(CobolFeature.MOVE, CobolFeature.GROUP_ITEM)
def test_group_sender_is_an_alphanumeric_move_into_any_receiver() -> None:
    """ANSI X3.23-1985 MOVE / IBM Enterprise COBOL LR "Group moves": a move
    whose sending item is a group is an alphanumeric-to-alphanumeric move with
    no conversion; the receiver is filled from the left and padded with spaces
    or truncated on the right, whatever its PICTURE (NIST-85 NC105A
    MOVE-TEST-F1-16, -17, -20, -38)."""
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "GRPMOVE"))

    assert ws.decode("cp037") == (
        "123ABC" "0123456789" "12" "123ABC " "123ABC " "0123456789   " "123ABC  "
    )
