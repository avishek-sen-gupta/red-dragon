"""A COMP-1 item occupies four bytes and a COMP-2 item eight, with no PICTURE:
storing into either leaves the items declared after it untouched."""

from __future__ import annotations

import struct

from interpreter.cobol.features import CobolFeature
from interpreter.encoding.ebcdic_table import EbcdicTable
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. FLTLAY.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 G USAGE COMP-2.",
    "01 H COMP-1.",
    "01 GRP.",
    "   05 GRP-D COMP-2.",
    "   05 GRP-S COMP-1.",
    "01 F1 PIC X VALUE 'P'.",
    "PROCEDURE DIVISION.",
    "    COMPUTE G = 1250.",
    "    COMPUTE H = 2.5.",
    "    COMPUTE GRP-D = 4.",
    "    COMPUTE GRP-S = 8.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_COMP_1, CobolFeature.USAGE_COMP_2, CobolFeature.COMPUTE)
def test_floating_point_items_are_laid_out_four_and_eight_bytes_wide() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "FLTLAY"))

    assert ws == (
        struct.pack(">d", 1250.0)
        + struct.pack(">f", 2.5)
        + struct.pack(">d", 4.0)
        + struct.pack(">f", 8.0)
        + bytes(EbcdicTable.ascii_to_ebcdic(b"P"))
    )
