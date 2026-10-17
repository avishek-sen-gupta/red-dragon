"""The lowered IR opens an absent OPTIONAL file with status 05: as an empty file for
INPUT, and created for I-O or EXTEND; an absent non-optional file fails with 35."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_PROGRAM = FileProgram(
    selects=(
        "    SELECT OPTIONAL INF ASSIGN TO INDD ORGANIZATION INDEXED",
        "        ACCESS DYNAMIC RECORD KEY INF-KEY FILE STATUS IS FS-IN.",
        "    SELECT OPTIONAL IOF ASSIGN TO IODD ORGANIZATION INDEXED",
        "        ACCESS DYNAMIC RECORD KEY IOF-KEY FILE STATUS IS FS-IO.",
        "    SELECT OPTIONAL EXF ASSIGN TO EXDD ORGANIZATION INDEXED",
        "        ACCESS SEQUENTIAL RECORD KEY EXF-KEY FILE STATUS IS FS-EX.",
        "    SELECT NOF ASSIGN TO NODD FILE STATUS IS FS-NO.",
        "    SELECT NIF ASSIGN TO NIDD ORGANIZATION INDEXED",
        "        ACCESS DYNAMIC RECORD KEY NIF-KEY FILE STATUS IS FS-NI.",
    ),
    fds=(
        "FD  INF.",
        "01  INF-REC.",
        "    05  INF-KEY PIC XX.",
        "FD  IOF.",
        "01  IOF-REC.",
        "    05  IOF-KEY PIC XX.",
        "FD  EXF.",
        "01  EXF-REC.",
        "    05  EXF-KEY PIC XX.",
        "FD  NOF.",
        "01  NOF-REC PIC XX.",
        "FD  NIF.",
        "01  NIF-REC.",
        "    05  NIF-KEY PIC XX.",
    ),
    working_storage=(
        "01  FS-IN PIC XX.",
        "01  FS-IO PIC XX.",
        "01  FS-EX PIC XX.",
        "01  FS-NO PIC XX.",
        "01  FS-NI PIC XX.",
    ),
    shared={"NIF": "nof.dat"},
)


@covers(CobolFeature.OPEN)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
def test_an_absent_optional_file_opens_with_status_05(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            Step("OPEN INPUT INF.", ("FS-IN",)),
            Step("READ INF NEXT.", ("FS-IN",)),
            Step("MOVE 'AB' TO INF-KEY READ INF.", ("FS-IN",)),
            Step("START INF KEY IS NOT LESS THAN INF-KEY.", ("FS-IN",)),
            Step("CLOSE INF.", ("FS-IN",)),
            Step("OPEN I-O IOF.", ("FS-IO",)),
            Step("MOVE 'AB' TO IOF-REC WRITE IOF-REC.", ("FS-IO",)),
            Step("CLOSE IOF.", ("FS-IO",)),
            Step("OPEN EXTEND EXF.", ("FS-EX",)),
            Step("MOVE 'CD' TO EXF-REC WRITE EXF-REC.", ("FS-EX",)),
            Step("CLOSE EXF.", ("FS-EX",)),
            Step("OPEN EXTEND EXF.", ("FS-EX",)),
            Step("MOVE 'EF' TO EXF-REC WRITE EXF-REC.", ("FS-EX",)),
            Step("CLOSE EXF.", ("FS-EX",)),
            Step("OPEN EXTEND NOF.", ("FS-NO",)),
            Step("OPEN I-O NIF.", ("FS-NI",)),
        ),
    )
    assert (
        statuses,
        (tmp_path / "inf.dat").exists(),
        (tmp_path / "iof.dat").read_bytes(),
        (tmp_path / "exf.dat").read_bytes(),
    ) == (
        ["05", "10", "23", "23", "00", "05", "00", "00"]
        + ["05", "00", "00", "00", "00", "00", "35", "35"],
        False,
        "AB".encode("cp037"),
        "CDEF".encode("cp037"),
    )
