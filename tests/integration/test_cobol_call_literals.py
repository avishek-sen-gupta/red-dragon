"""A literal CALL argument arrives in the representation IBM defines for it.

BY VALUE: a fixed-point numeric literal as a fullword binary, ZERO as a binary
zero, a floating-point literal as COMP-2. A figurative constant: one byte of its
character -- SPACE is an EBCDIC space, HIGH-VALUE the raw byte 0xFF -- never the
word written in the source.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. LITM.",
    "PROCEDURE DIVISION.",
    "    CALL 'LITS' USING BY VALUE 7 BY VALUE -12",
    "        BY VALUE ZERO",
    "        BY CONTENT SPACES BY CONTENT HIGH-VALUE",
    "        BY VALUE 1.5E2.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. LITS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-A     PIC 9(4).",
    "01 WS-B     PIC S9(4) SIGN LEADING SEPARATE.",
    "01 WS-C     PIC 9(4).",
    "01 WS-D     PIC X(1).",
    "01 WS-E     PIC X(1).",
    "01 WS-F     PIC 9(4).",
    "01 WS-HIGH  PIC X(1) VALUE HIGH-VALUE.",
    "LINKAGE SECTION.",
    "01 LK-A     PIC S9(9) COMP-5.",
    "01 LK-B     PIC S9(9) COMP-5.",
    "01 LK-C     PIC S9(9) COMP-5.",
    "01 LK-D     PIC X(1).",
    "01 LK-E     PIC X(1).",
    "01 LK-F     COMP-2.",
    "PROCEDURE DIVISION USING LK-A LK-B LK-C LK-D LK-E LK-F.",
    "    MOVE LK-A TO WS-A.",
    "    MOVE LK-B TO WS-B.",
    "    MOVE LK-C TO WS-C.",
    "    MOVE LK-D TO WS-D.",
    "    IF LK-E = WS-HIGH MOVE 'H' TO WS-E.",
    "    MOVE LK-F TO WS-F.",
    "    GOBACK.",
]


@covers(CobolFeature.CALL_USING_LITERAL)
def test_each_literal_argument_arrives_as_its_ibm_representation() -> None:
    ws = bytes(ws_region(run_cobol_programs(_MAIN, {"LITS": _SUB}), "LITS"))

    assert (ws[:13].decode("cp037"), ws[13:15], ws[15:19].decode("cp037")) == (
        "0007-00120000",
        b"\x40\xc8",
        "0150",
    )
