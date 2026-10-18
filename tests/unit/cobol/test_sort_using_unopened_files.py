"""SORT transfers records only from and to the USING and GIVING files its implicit OPEN
opened, and leaves each file the I-O status that OPEN and CLOSE would."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_PROGRAM = FileProgram(
    selects=(
        '    SELECT MISS-F ASSIGN TO "MISSF" FILE STATUS IS FS-MI.',
        '    SELECT OPTIONAL OPT-F ASSIGN TO "OPTF" FILE STATUS IS FS-OP.',
        '    SELECT IN-F ASSIGN TO "INF" FILE STATUS IS FS-IN.',
        '    SELECT OUT-F ASSIGN TO "OUTF" FILE STATUS IS FS-OU.',
        '    SELECT BAD-F ASSIGN TO "BADF" FILE STATUS IS FS-BA.',
        '    SELECT SRT ASSIGN TO "SRT".',
    ),
    fds=(
        "FD  MISS-F.",
        "01  MISS-REC PIC XX.",
        "FD  OPT-F.",
        "01  OPT-REC PIC XX.",
        "FD  IN-F.",
        "01  IN-REC PIC XX.",
        "FD  OUT-F.",
        "01  OUT-REC PIC XX.",
        "FD  BAD-F.",
        "01  BAD-REC PIC XX.",
        "SD  SRT.",
        "01  SRT-REC.",
        "    05  S-KEY PIC X.",
        "    05  S-TAG PIC X.",
    ),
    working_storage=(
        "01  FS-MI PIC XX.",
        "01  FS-OP PIC XX.",
        "01  FS-IN PIC XX.",
        "01  FS-OU PIC XX.",
        "01  FS-BA PIC XX.",
    ),
    shared={"BAD-F": "no-such-directory/badf"},
)


@covers(CobolFeature.SORT)
def test_sort_transfers_only_through_the_files_its_open_opened(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            Step(
                "OPEN OUTPUT IN-F.\nMOVE 'B1' TO IN-REC WRITE IN-REC.\n"
                "MOVE 'A2' TO IN-REC WRITE IN-REC.\nCLOSE IN-F.",
                ("FS-IN",),
            ),
            Step(
                "SORT SRT ON ASCENDING KEY S-KEY\n"
                "    USING MISS-F OPT-F IN-F GIVING OUT-F BAD-F.",
                ("FS-MI", "FS-OP", "FS-IN", "FS-OU", "FS-BA"),
            ),
            Step("OPEN INPUT OUT-F.", ("FS-OU",)),
            Step("READ OUT-F.", ("FS-OU", "OUT-REC")),
            Step("READ OUT-F.", ("FS-OU", "OUT-REC")),
            Step("READ OUT-F.", ("FS-OU",)),
            Step("CLOSE OUT-F.", ("FS-OU",)),
        ),
    )
    assert (statuses, (tmp_path / "OPTF").exists()) == (
        ["00", "35", "00", "00", "00", "35", "00", "00", "A2", "00", "B1", "10", "00"],
        False,
    )
