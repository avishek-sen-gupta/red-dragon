"""A COMP-5 item is a binary halfword, fullword or doubleword by its digit count,
like COMP: the items declared after it start right after those bytes."""

from __future__ import annotations

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. C5LAY.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 H PIC S9(4) COMP-5.",
    "01 GRP.",
    "   05 GRP-F PIC S9(9) COMP-5.",
    "   05 GRP-D PIC 9(18) COMP-5.",
    "01 F1 PIC X VALUE 'P'.",
    "PROCEDURE DIVISION.",
    "    MOVE -20 TO H.",
    "    MOVE 7 TO GRP-F.",
    "    MOVE 9 TO GRP-D.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_COMP, CobolFeature.MOVE)
def test_comp5_items_are_laid_out_two_four_and_eight_bytes_wide() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "C5LAY"))

    assert ws == (
        (-20).to_bytes(2, "big", signed=True)
        + (7).to_bytes(4, "big", signed=True)
        + (9).to_bytes(8, "big")
        + bytes(EbcdicTable.ascii_to_ebcdic(b"P"))
    )
