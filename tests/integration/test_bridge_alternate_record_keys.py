"""Every ALTERNATE RECORD KEY of a file control entry, qualified or not, with its
DUPLICATES phrase, reaches the typed ASG in the order written."""

from __future__ import annotations

from cobol_asg.alternate_record_key import AlternateRecordKey
from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ALTKEYS.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F ASSIGN TO XXXXX001 ORGANIZATION IS INDEXED",
    "        RECORD KEY IS K IN PK",
    "        ALTERNATE RECORD KEY IS K OF AK1",
    "        ALTERNATE RECORD KEY IS K IN AK2 WITH DUPLICATES",
    "        ALTERNATE KEY F-ALT DUPLICATES.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  F.",
    "01  F-REC.",
    "    05 PK. 10 K PIC X.",
    "    05 AK1. 10 K PIC X.",
    "    05 AK2. 10 K PIC X.",
    "    05 F-ALT PIC X.",
    "PROCEDURE DIVISION.",
    "MAIN-P.",
    "    STOP RUN.",
]


@covers(CobolFeature.START)
def test_each_alternate_record_key_is_kept_in_the_asg() -> None:
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    (entry,) = make_cobol_parser().parse(source).first_program.file_control
    assert entry.alternate_keys == (
        AlternateRecordKey(RefModOperand(name="K", qualifiers=("AK1",)), False),
        AlternateRecordKey(RefModOperand(name="K", qualifiers=("AK2",)), True),
        AlternateRecordKey(RefModOperand(name="F-ALT"), True),
    )
