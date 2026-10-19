"""An elementary sender moved to a group receiver copies its stored bytes, sign and usage included."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. GRPRECV.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 N-LEAD PIC S9(5) SIGN IS LEADING SEPARATE VALUE 7.",
    "01 N-TRAIL PIC S9(5) SIGN IS TRAILING SEPARATE VALUE -7.",
    "01 N-OVER PIC S9(5) VALUE -7.",
    "01 N-PACKED PIC S9(3) COMP-3 VALUE -7.",
    "01 N-BINARY PIC S9(4) COMP VALUE 7.",
    "01 N-LONG PIC 9(8) VALUE 12345678.",
    "01 G-LEAD.",
    "   02 G-LEAD-A PIC X(7).",
    "01 G-TRAIL.",
    "   02 G-TRAIL-A PIC X(7).",
    "01 G-OVER.",
    "   02 G-OVER-A PIC X(7).",
    "01 G-PACKED.",
    "   02 G-PACKED-A PIC X(7).",
    "01 G-BINARY.",
    "   02 G-BINARY-A PIC X(7).",
    "01 G-LONG.",
    "   02 G-LONG-A PIC X(4).",
    "01 X-LEAD PIC X(6).",
    "01 R-OVER PIC S9(5).",
    "01 R-PACKED PIC S9(3) COMP-3.",
    "PROCEDURE DIVISION.",
    "    MOVE N-LEAD TO G-LEAD X-LEAD.",
    "    MOVE N-TRAIL TO G-TRAIL.",
    "    MOVE N-OVER TO G-OVER.",
    "    MOVE N-PACKED TO G-PACKED.",
    "    MOVE N-BINARY TO G-BINARY.",
    "    MOVE N-LONG TO G-LONG.",
    "    MOVE G-OVER TO R-OVER.",
    "    MOVE G-PACKED TO R-PACKED.",
    "    STOP RUN.",
]

_PACKED = b"\x00\x7d"
_BINARY = b"\x00\x07"
_SPACES = "     ".encode("cp037")


@covers(CobolFeature.MOVE, CobolFeature.GROUP_ITEM)
def test_elementary_sender_fills_a_group_receiver_with_its_stored_bytes() -> None:
    """IBM Enterprise COBOL LR "Group moves" / ANSI X3.23-1985 MOVE: a move to
    a group receiver is an alphanumeric move with no conversion of internal
    representation, so a separate sign, an overpunched sign, packed and binary
    bytes all arrive as stored, padded with spaces or truncated on the right;
    an elementary receiver still takes the digit image, and a group sender
    fills a numeric receiver byte for byte (NIST-85 SQ111A)."""
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "GRPRECV"))

    senders = "+00007" "00007-" "0000P".encode("cp037") + _PACKED + _BINARY
    receivers = (
        "+00007 "
        "00007- "
        "0000P  ".encode("cp037") + _PACKED + _SPACES + _BINARY + _SPACES + "1234"
        "00007 "
        "0000P".encode("cp037") + _PACKED
    )
    assert ws == senders + "12345678".encode("cp037") + receivers
