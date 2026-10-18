# pyright: standard
"""The EXTERNAL clause of a WORKING-STORAGE 01 and of an FD, read from the bridge and
kept through a round trip of the ASG (red-dragon-ljku.3)."""

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTITEMS.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD.
           SELECT OWN-FILE ASSIGN TO OWNDD.
       DATA DIVISION.
       FILE SECTION.
       FD  SHARED-FILE IS EXTERNAL.
       01  SHARED-REC        PIC X(10).
       FD  OWN-FILE.
       01  OWN-REC           PIC X(10).
       WORKING-STORAGE SECTION.
       01  SHARED-DATA IS EXTERNAL.
           05  SHARED-PART   PIC X(4).
       01  OWN-DATA          PIC X(4).
       PROCEDURE DIVISION.
           STOP RUN.
"""


def _flags(asg: CobolASG) -> tuple[dict[str, bool], dict[str, bool]]:
    return (
        {
            item.name: item.external
            for top in asg.data_fields
            for item in (top, *top.children)
        },
        {fd.fd_name: fd.external for fd in asg.file_descriptions},
    )


@covers(CobolFeature.EXTERNAL_DATA, CobolFeature.EXTERNAL_FILE)
def test_external_records_and_files_are_read_and_survive_a_round_trip():
    asg = make_cobol_parser().parse(_SOURCE).first_program
    expected = (
        {"SHARED-DATA": True, "SHARED-PART": False, "OWN-DATA": False},
        {"SHARED-FILE": True, "OWN-FILE": False},
    )

    assert (_flags(asg), _flags(CobolASG.from_dict(asg.to_dict()))) == (
        expected,
        expected,
    )
