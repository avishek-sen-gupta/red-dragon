"""READ's NEXT phrase reaches the typed ASG; the optional word RECORD is not NEXT."""

from __future__ import annotations

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import ReadStatement
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RDNEXT.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F ASSIGN TO XXXXX001 ORGANIZATION IS RELATIVE",
    "        ACCESS MODE IS DYNAMIC RELATIVE KEY IS RK.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  F.",
    "01  F-REC PIC X(10).",
    "WORKING-STORAGE SECTION.",
    "01  RK PIC 9(4).",
    "PROCEDURE DIVISION.",
    "MAIN-P.",
    "    READ F.",
    "    READ F RECORD.",
    "    READ F NEXT.",
    "    READ F NEXT RECORD.",
    "    STOP RUN.",
]


@covers(CobolFeature.READ)
def test_only_the_next_phrase_makes_a_read_sequential() -> None:
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    statements = (
        make_cobol_parser().parse(source).first_program.paragraphs[0].statements
    )
    assert [s.next_record for s in statements if isinstance(s, ReadStatement)] == [
        False,
        False,
        True,
        True,
    ]
