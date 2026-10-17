"""RealFileIOProvider opens an absent OPTIONAL file with status 05: as an empty file
for INPUT, and created for I-O or EXTEND; an absent non-optional file fails with 35."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

_SEQ = "SEQUENTIAL"
_INDEXED = "INDEXED"
_DYNAMIC = "DYNAMIC"


@covers(CobolFeature.OPEN)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
def test_an_absent_optional_file_opens_with_status_05(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    statuses = [
        prov._open_file("IN", "INPUT", 2, _INDEXED, 0, 2, _DYNAMIC, 0, True, "P"),
        prov._read_record("IN", "", "P"),
        prov._read_record("IN", "AB", "P"),
        prov._start_file("IN", "AB", ">=", "P"),
        prov._close_file("IN", "P"),
        prov._open_file("IO", "I-O", 2, _INDEXED, 0, 2, _DYNAMIC, 0, True, "P"),
        prov._write_record("IO", "AB", "", "P"),
        prov._close_file("IO", "P"),
        prov._open_file("EX", "EXTEND", 2, _INDEXED, 0, 2, _SEQ, 0, True, "P"),
        prov._write_record("EX", "CD", "", "P"),
        prov._close_file("EX", "P"),
        prov._open_file("EX", "EXTEND", 2, _INDEXED, 0, 2, _SEQ, 0, True, "P"),
        prov._write_record("EX", "EF", "", "P"),
        prov._close_file("EX", "P"),
        prov._open_file("NO", "EXTEND", 2, _SEQ, 0, 0, _SEQ, 0, False, "P"),
        prov._open_file("NO", "I-O", 2, _INDEXED, 0, 2, _DYNAMIC, 0, False, "P"),
    ]
    assert (
        [result.status for result in statuses],
        (tmp_path / "in.dat").exists(),
        (tmp_path / "io.dat").read_bytes(),
        (tmp_path / "ex.dat").read_bytes(),
    ) == (
        ["05", "10", "23", "23", "00"]
        + ["05", "00", "00"]
        + ["05", "00", "00", "00", "00", "00"]
        + ["35", "35"],
        False,
        b"AB",
        b"CDEF",
    )
