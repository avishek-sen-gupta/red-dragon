# pyright: standard
"""Which file each FD record belongs to, read from the bridge and kept through a round
trip of the ASG, so a consumer of a cached ASG can still name the file a WRITE goes to.
"""

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FDPAIRS.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO INDD.
           SELECT OUT-FILE ASSIGN TO OUTDD.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE.
       01  IN-REC            PIC X(10).
       FD  OUT-FILE.
       01  OUT-HEADER        PIC X(10).
       01  OUT-DETAIL.
           05  OUT-KEY       PIC X(4).
       PROCEDURE DIVISION.
           STOP RUN.
"""


@covers(CobolFeature.SECTION_FILE)
def test_each_fd_record_keeps_its_file_through_a_round_trip():
    asg = make_cobol_parser().parse(_SOURCE).first_program
    expected = {"IN-REC": "IN-FILE", "OUT-HEADER": "OUT-FILE", "OUT-DETAIL": "OUT-FILE"}

    assert (
        asg.file_record_to_select,
        CobolASG.from_dict(asg.to_dict()).file_record_to_select,
    ) == (expected, expected)
