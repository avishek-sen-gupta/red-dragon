"""Every USE AFTER ERROR target reaches the typed ASG, EXTEND included."""

from __future__ import annotations

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. USETGT.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F1 ASSIGN TO XXXXX001.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  F1.",
    "01  F1-REC PIC X(10).",
    "PROCEDURE DIVISION.",
    "DECLARATIVES.",
    "D-IN SECTION.",
    "    USE AFTER STANDARD ERROR PROCEDURE ON INPUT.",
    "D-OUT SECTION.",
    "    USE AFTER ERROR PROCEDURE OUTPUT.",
    "D-IO SECTION.",
    "    USE AFTER EXCEPTION PROCEDURE I-O.",
    "D-EXT SECTION.",
    "    USE AFTER EXCEPTION PROCEDURE EXTEND.",
    "D-F1 SECTION.",
    "    USE AFTER STANDARD EXCEPTION PROCEDURE ON F1.",
    "END DECLARATIVES.",
    "MAIN SECTION.",
    "MAIN-P.",
    "    STOP RUN.",
]


@covers(CobolFeature.DECLARATIVES)
def test_each_use_target_is_kept_in_the_asg() -> None:
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    asg = make_cobol_parser().parse(source).first_program
    assert [
        (s.name, s.use.target if s.use else "", s.use.files if s.use else ())
        for s in asg.declaratives
    ] == [
        ("D-IN", "INPUT", ()),
        ("D-OUT", "OUTPUT", ()),
        ("D-IO", "I-O", ()),
        ("D-EXT", "EXTEND", ()),
        ("D-F1", "FILE", ("F1",)),
    ]
