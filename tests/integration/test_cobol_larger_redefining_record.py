"""A redefining 01 may be larger than the 01 it redefines: the shared area is
as long as the longest of them, and the next 01 starts after it."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. BIGRDF.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-SMALL PIC X(4) VALUE 'ABCD'.",
    "01 WS-BIG REDEFINES WS-SMALL PIC X(10).",
    "01 WS-MID REDEFINES WS-SMALL PIC X(7).",
    "01 WS-NEXT PIC X(6) VALUE 'XYZXYZ'.",
    "PROCEDURE DIVISION.",
    "    MOVE ALL '*' TO WS-BIG.",
    "    MOVE ALL '-' TO WS-MID.",
    "    STOP RUN.",
]


@covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
def test_a_larger_redefining_record_does_not_overlap_the_next_record() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "BIGRDF"))

    assert (len(ws), ws.decode("cp037")) == (16, "-------***XYZXYZ")
