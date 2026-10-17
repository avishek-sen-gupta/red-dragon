"""A suppression run after a leading decimal point, and insertion inside a run, end to end."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. EDITRUNS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-ZERO PIC $.** VALUE ZERO.",
    "01 WS-CENTS PIC $.**.",
    "01 WS-PROTECTED PIC -*B*99.",
    "01 WS-FLAG PIC X VALUE 'N'.",
    "PROCEDURE DIVISION.",
    "    MOVE .05 TO WS-CENTS.",
    "    MOVE -42 TO WS-PROTECTED.",
    "    IF WS-ZERO = '*.**' MOVE 'Y' TO WS-FLAG.",
    "    STOP RUN.",
]


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.PIC_CLAUSE)
def test_suppression_after_the_point_and_insertion_within_a_run() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "EDITRUNS"))

    assert ws.decode("cp037") == "*.**$.05-***42Y"
