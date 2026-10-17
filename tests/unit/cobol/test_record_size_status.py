"""A WRITE or REWRITE of a variable-length record shorter than the file's smallest or
longer than its largest record is a boundary violation, status 44."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_PROGRAM = FileProgram(
    selects=("    SELECT VF ASSIGN TO VDD FILE STATUS IS FS-V.",),
    fds=(
        "FD  VF RECORD IS VARYING IN SIZE FROM 2 TO 4 CHARACTERS",
        "    DEPENDING ON V-LEN.",
        "01  V-REC PIC X(4).",
    ),
    working_storage=("01  FS-V PIC XX.", "01  V-LEN PIC 9."),
)


def _v(statement: str) -> Step:
    return Step(statement, ("FS-V",))


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
def test_a_record_outside_the_files_sizes_is_status_44(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            _v("OPEN OUTPUT VF."),
            _v("MOVE 1 TO V-LEN MOVE 'A' TO V-REC WRITE V-REC."),
            _v("MOVE 5 TO V-LEN MOVE 'ABCD' TO V-REC WRITE V-REC."),
            _v("MOVE 3 TO V-LEN MOVE 'ABC' TO V-REC WRITE V-REC."),
            _v("CLOSE VF."),
            _v("OPEN I-O VF."),
            _v("READ VF."),
            _v("MOVE 5 TO V-LEN REWRITE V-REC."),
            _v("CLOSE VF."),
        ),
    )
    assert (statuses, (tmp_path / "vf.dat").read_bytes()) == (
        ["00", "44", "44", "00", "00", "00", "00", "44", "00"],
        b"\x00\x07\x00\x00" + "ABC".encode("cp037"),
    )
