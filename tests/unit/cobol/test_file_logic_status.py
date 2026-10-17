"""The lowered IR reports the ANSI X3.23-1985 logic-error I-O statuses (4x) and 38."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_PROGRAM = FileProgram(
    selects=(
        "    SELECT F ASSIGN TO FDD FILE STATUS IS FS-F.",
        "    SELECT G ASSIGN TO GDD FILE STATUS IS FS-G.",
    ),
    fds=("FD  F.", "01  F-REC PIC X(4).", "FD  G.", "01  G-REC PIC X(4)."),
    working_storage=("01  FS-F PIC XX.", "01  FS-G PIC XX."),
)


def _f(statement: str) -> Step:
    return Step(statement, ("FS-F",))


def _g(statement: str) -> Step:
    return Step(statement, ("FS-G",))


_ONE_RECORD_FILE = (
    _f("OPEN OUTPUT F."),
    _f("MOVE 'AAAA' TO F-REC WRITE F-REC."),
    _f("CLOSE F."),
)


@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
def test_open_of_an_open_file_and_close_of_a_closed_file(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            *_ONE_RECORD_FILE,
            _f("CLOSE F."),
            _f("OPEN INPUT F."),
            _f("OPEN I-O F."),
            _f("WRITE F-REC."),
            _f("CLOSE F."),
            _f("CLOSE F."),
        ),
    )
    assert statuses == ["00", "00", "00", "42", "00", "41", "48", "00", "42"]


@covers(CobolFeature.READ)
def test_read_needs_an_input_mode_and_a_next_record(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            *_ONE_RECORD_FILE,
            _f("READ F."),
            _f("OPEN EXTEND F."),
            _f("READ F."),
            _f("CLOSE F."),
            _f("OPEN INPUT F."),
            _f("READ F."),
            _f("READ F."),
            _f("READ F."),
        ),
    )
    assert statuses == [
        "00",
        "00",
        "00",
        "47",
        "00",
        "47",
        "00",
        "00",
        "00",
        "10",
        "46",
    ]


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
def test_write_and_rewrite_need_their_open_modes_and_a_current_record(
    tmp_path: Path,
) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            *_ONE_RECORD_FILE,
            _f("MOVE 'BBBB' TO F-REC WRITE F-REC."),
            _f("REWRITE F-REC."),
            _f("DELETE F."),
            _f("OPEN INPUT F."),
            _f("REWRITE F-REC."),
            _f("CLOSE F."),
            _f("OPEN I-O F."),
            _f("MOVE 'BBBB' TO F-REC WRITE F-REC."),
            _f("REWRITE F-REC."),
            _f("READ F."),
            _f("MOVE 'CCCC' TO F-REC REWRITE F-REC."),
            _f("MOVE 'DDDD' TO F-REC REWRITE F-REC."),
            _f("READ F."),
            _f("MOVE 'EEEE' TO F-REC REWRITE F-REC."),
            _f("CLOSE F."),
        ),
    )
    assert (statuses, (tmp_path / "f.dat").read_bytes()) == (
        [
            "00",
            "00",
            "00",
            "48",
            "49",
            "49",
            "00",
            "49",
            "00",
            "00",
            "48",
            "43",
            "00",
            "00",
            "43",
            "10",
            "43",
            "00",
        ],
        "CCCC".encode("cp037"),
    )


@covers(CobolFeature.CLOSE)
def test_a_file_closed_with_lock_cannot_be_opened_again(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            *_ONE_RECORD_FILE,
            _f("OPEN INPUT F."),
            _g("OPEN OUTPUT G."),
            _f("CLOSE F WITH LOCK."),
            _f("OPEN INPUT F."),
            _f("OPEN EXTEND F."),
            _f("CLOSE F WITH LOCK."),
            _g("CLOSE G."),
            _g("OPEN INPUT G."),
        ),
    )
    assert statuses == [
        "00",
        "00",
        "00",
        "00",
        "00",
        "00",
        "38",
        "38",
        "42",
        "00",
        "00",
    ]
