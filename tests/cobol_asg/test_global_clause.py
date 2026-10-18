# pyright: standard
"""The GLOBAL clause of a WORKING-STORAGE 01 and of an FD, and the programs that
contain a contained program, read from the bridge (red-dragon-ljku.4)."""

import json
from pathlib import Path

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.compilation_unit import programs_in_preorder
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. OUTER.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD.
           SELECT OWN-FILE ASSIGN TO OWNDD.
       DATA DIVISION.
       FILE SECTION.
       FD  SHARED-FILE GLOBAL.
       01  SHARED-REC        PIC X(10).
       FD  OWN-FILE.
       01  OWN-REC           PIC X(10).
       WORKING-STORAGE SECTION.
       01  SHARED-DATA IS GLOBAL.
           05  SHARED-PART   PIC X(4).
       01  OWN-DATA          PIC X(4).
       PROCEDURE DIVISION.
           STOP RUN.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MIDDLE.
       PROCEDURE DIVISION.
           GOBACK.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INNER.
       PROCEDURE DIVISION.
           GOBACK.
       END PROGRAM INNER.
       END PROGRAM MIDDLE.
       END PROGRAM OUTER.
"""


def _flags(asg: CobolASG) -> tuple[dict[str, bool], dict[str, bool]]:
    return (
        {
            item.name: item.is_global
            for top in asg.data_fields
            for item in (top, *top.children)
        },
        {fd.fd_name: fd.is_global for fd in asg.file_descriptions},
    )


@covers(CobolFeature.GLOBAL_DATA, CobolFeature.GLOBAL_FILE)
def test_global_items_and_each_programs_enclosing_programs_are_read(tmp_path: Path):
    written = make_cobol_parser().parse_to_file(_SOURCE, tmp_path / "unit.json")
    inner = CobolASG.from_dict(programs_in_preorder(json.loads(written.read_text()))[2])
    outer_flags = (
        {"SHARED-DATA": True, "SHARED-PART": False, "OWN-DATA": False},
        {"SHARED-FILE": True, "OWN-FILE": False},
    )

    assert (
        inner.program_id,
        [e.program_id for e in inner.enclosing],
        _flags(inner.enclosing[1]),
        _flags(CobolASG.from_dict(inner.to_dict()).enclosing[1]),
    ) == ("INNER", ["MIDDLE", "OUTER"], outer_flags, outer_flags)
