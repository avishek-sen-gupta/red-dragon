"""EXIT PERFORM leaves the innermost inline PERFORM; EXIT PERFORM CYCLE ends only
the current iteration, so the loop's own step -- the TIMES count, the VARYING
increment, the UNTIL test -- still runs.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
)

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. EXITPF.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "77 WS-I     PIC 9 VALUE 0.",
    "77 WS-N     PIC 9 VALUE 0.",
    "77 WS-S     PIC 9 VALUE 0.",
    "77 WS-K     PIC 9 VALUE 0.",
    "77 WS-L     PIC 9 VALUE 0.",
    "PROCEDURE DIVISION.",
    "P1.",
    "    PERFORM 5 TIMES",
    "        ADD 1 TO WS-I",
    "        IF WS-I = 2",
    "            EXIT PERFORM CYCLE",
    "        END-IF",
    "        IF WS-I = 4",
    "            EXIT PERFORM",
    "        END-IF",
    "        ADD 1 TO WS-N",
    "    END-PERFORM.",
    "    PERFORM VARYING WS-K FROM 1 BY 1 UNTIL WS-K > 5",
    "        IF WS-K = 3",
    "            EXIT PERFORM CYCLE",
    "        END-IF",
    "        ADD 1 TO WS-S",
    "    END-PERFORM.",
    "    PERFORM UNTIL WS-L > 2",
    "        ADD 1 TO WS-L",
    "        EXIT PERFORM",
    "    END-PERFORM.",
    "    STOP RUN.",
]


@covers(
    CobolFeature.EXIT_PERFORM,
    CobolFeature.PERFORM_TIMES,
    CobolFeature.PERFORM_VARYING,
    CobolFeature.PERFORM_UNTIL,
    CobolFeature.PERFORM_INLINE,
)
def test_exit_perform_leaves_the_loop_and_cycle_ends_the_iteration() -> None:
    region = first_region(run_cobol(_PROGRAM, max_steps=20000))
    assert isinstance(region, bytearray)

    assert [decode_zoned_unsigned(region, offset, 1) for offset in range(5)] == [
        4,
        2,
        4,
        6,
        1,
    ]
