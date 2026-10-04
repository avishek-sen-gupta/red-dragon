"""A USAGE POINTER field takes the addressing mode's width: 4 bytes under
LP(32), 8 under LP(64), so the item after it moves accordingly."""

from cobol_asg.lp import LP
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRFLD.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-P USAGE POINTER.",
    "01 WS-X PIC X(2) VALUE 'AB'.",
    "PROCEDURE DIVISION.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_POINTER)
def test_a_pointer_field_is_as_wide_as_the_addressing_mode() -> None:
    def offset_of_x(lp: LP) -> int:
        ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}, lp=lp), "PTRFLD"))
        return ws.index(b"\xc1\xc2")

    assert (offset_of_x(LP.LP32), offset_of_x(LP.LP64)) == (4, 8)
