"""A WRITE or REWRITE of a variable-length record shorter than the file's smallest or
longer than its largest record is a boundary violation, status 44."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

_SEQ = "SEQUENTIAL"


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
def test_a_record_outside_the_files_sizes_is_status_44(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    prov._open_file("V", "OUTPUT", 4, _SEQ, 0, 0, _SEQ, 0, False, True, 2, "P")
    writes = [
        prov._write_record("V", data, "", "P").status for data in ("A", "ABCDE", "ABC")
    ]
    prov._close_file("V", "P")
    prov._open_file("V", "I-O", 4, _SEQ, 0, 0, _SEQ, 0, False, True, 2, "P")
    prov._read_record("V", "", "P")
    rewrite = prov._rewrite_record("V", "ABCDE", "", "P").status
    prov._close_file("V", "P")
    assert (writes, rewrite, (tmp_path / "v.dat").read_bytes()) == (
        ["44", "44", "00"],
        "44",
        b"\x00\x07\x00\x00ABC",
    )
