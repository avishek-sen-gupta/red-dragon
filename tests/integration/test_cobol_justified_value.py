"""A VALUE initialises a JUSTIFIED RIGHT item left-aligned: the clause governs
MOVE, and initialisation is independent of it."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. JUSTVAL.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-INIT PIC X(4) JUSTIFIED RIGHT VALUE 'XY'.",
    "01 WS-MOVED PIC X(4) JUSTIFIED RIGHT VALUE 'XY'.",
    "PROCEDURE DIVISION.",
    "    MOVE 'AB' TO WS-MOVED.",
    "    STOP RUN.",
]


@covers(CobolFeature.JUSTIFIED_CLAUSE, CobolFeature.VALUE_CLAUSE)
def test_a_value_is_not_justified_but_a_move_is() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "JUSTVAL"))

    assert ws.decode("cp037") == "XY    AB"
