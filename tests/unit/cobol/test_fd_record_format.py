"""Whether an FD's records vary in length: RECORDING MODE when coded, else the RECORD
clause, else whether its record descriptions differ in length; the RECORD VARYING
clause's DEPENDING ON item; and the size of its smallest record."""

from __future__ import annotations

from interpreter.cobol.fd_record_format import (
    depending_on,
    minimum_length,
    records_vary,
)
from interpreter.cobol.features import CobolFeature
from interpreter.frontend import make_cobol_parser
from tests.covers import covers

_FDS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FDVARY.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CODED-F ASSIGN TO D1.
           SELECT CODED-V ASSIGN TO D2.
           SELECT SIZED ASSIGN TO D3.
           SELECT SAME-RANGE ASSIGN TO D4.
           SELECT RANGED ASSIGN TO D5.
           SELECT VARIED ASSIGN TO D6.
           SELECT ONE-LENGTH ASSIGN TO D7.
           SELECT TWO-LENGTHS ASSIGN TO D8.
       DATA DIVISION.
       FILE SECTION.
       FD  CODED-F RECORDING MODE IS F.
       01  CF-A PIC X(4).
       01  CF-B PIC X(6).
       FD  CODED-V RECORDING MODE IS V.
       01  CV-A PIC X(4).
       FD  SIZED RECORD CONTAINS 6 CHARACTERS.
       01  SZ-A PIC X(4).
       01  SZ-B PIC X(6).
       FD  SAME-RANGE RECORD CONTAINS 4 TO 4 CHARACTERS.
       01  SR-A PIC X(4).
       FD  RANGED RECORD CONTAINS 4 TO 6 CHARACTERS.
       01  RG-A PIC X(4).
       01  RG-B PIC X(6).
       FD  VARIED RECORD IS VARYING IN SIZE FROM 1 TO 6
               DEPENDING ON VY-LEN.
       01  VY-A PIC X(6).
       FD  ONE-LENGTH.
       01  OL-A PIC X(4).
       01  OL-B PIC X(4).
       FD  TWO-LENGTHS.
       01  TL-A PIC X(4).
       01  TL-B PIC X(6).
       WORKING-STORAGE SECTION.
       01  VY-LEN PIC 9.
       PROCEDURE DIVISION.
           GOBACK.
"""

_FILES = (
    "CODED-F",
    "CODED-V",
    "SIZED",
    "SAME-RANGE",
    "RANGED",
    "VARIED",
    "ONE-LENGTH",
    "TWO-LENGTHS",
)


@covers(CobolFeature.SECTION_FILE)
def test_an_fds_records_vary_by_mode_clause_or_descriptions() -> None:
    asg = make_cobol_parser().parse(_FDS)
    assert (
        [records_vary(asg, f) for f in _FILES],
        [depending_on(asg, f) for f in _FILES],
        [minimum_length(asg, f) for f in _FILES],
    ) == (
        [False, True, False, False, True, True, False, True],
        ["", "", "", "", "", "VY-LEN", "", ""],
        [4, 4, 4, 4, 4, 1, 4, 4],
    )
