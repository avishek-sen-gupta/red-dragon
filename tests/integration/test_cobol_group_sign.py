"""A group's SIGN clause applies to its signed DISPLAY numeric items, and the nearest SIGN clause wins."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. GRPSIGN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 OUTER SIGN TRAILING SEPARATE.",
    "   03 A PIC S9(2).",
    "   03 INNER SIGN LEADING SEPARATE.",
    "      05 B PIC S9(2).",
    "      05 C PIC S9(2) SIGN TRAILING.",
    "      05 D PIC 9(2).",
    "      05 E PIC S9(2) COMP.",
    "PROCEDURE DIVISION.",
    "    MOVE -12 TO A.",
    "    MOVE 34 TO B.",
    "    MOVE -56 TO C.",
    "    MOVE 78 TO D.",
    "    MOVE 9 TO E.",
    "    STOP RUN.",
]


@covers(CobolFeature.SIGN_CLAUSE, CobolFeature.GROUP_ITEM)
def test_group_sign_is_inherited_by_signed_display_items() -> None:
    """ANSI X3.23-1985 / ISO 1989 SIGN clause (VI-42 5.12.4): a SIGN clause on a
    group applies to each signed numeric DISPLAY item subordinate to it, unless
    that item, or a group nearer to it, has a SIGN clause of its own. Unsigned
    and non-DISPLAY items are unaffected."""
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "GRPSIGN"))

    assert ws.hex() == "f1f260" "4ef3f4" "f5d6" "f7f8" "0009"
