"""RealFileIOProvider opens an absent OPTIONAL file with status 05: as an empty file
for INPUT, and created for I-O or EXTEND; an absent non-optional file fails with 35."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers
from tests.unit.cobol.declared_files import opened

_SEQ = "SEQUENTIAL"
_INDEXED = "INDEXED"
_DYNAMIC = "DYNAMIC"


@covers(CobolFeature.OPEN)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
def test_an_absent_optional_file_opens_with_status_05(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    statuses = [
        opened(
            prov,
            "INPUT",
            FileFrame(
                "IN",
                FileOrganization(_INDEXED),
                AccessMode(_DYNAMIC),
                PrimeKey(0, 2),
                0,
                True,
                False,
                0,
                2,
            ),
        ),
        prov._read_record("IN", "", "P"),
        prov._read_record("IN", "AB", "P"),
        prov._start_file("IN", "AB", ">=", "P"),
        prov._close_file("IN", "P"),
        opened(
            prov,
            "I-O",
            FileFrame(
                "IO",
                FileOrganization(_INDEXED),
                AccessMode(_DYNAMIC),
                PrimeKey(0, 2),
                0,
                True,
                False,
                0,
                2,
            ),
        ),
        prov._write_record("IO", "AB", "", "P"),
        prov._close_file("IO", "P"),
        opened(
            prov,
            "EXTEND",
            FileFrame(
                "EX",
                FileOrganization(_INDEXED),
                AccessMode(_SEQ),
                PrimeKey(0, 2),
                0,
                True,
                False,
                0,
                2,
            ),
        ),
        prov._write_record("EX", "CD", "", "P"),
        prov._close_file("EX", "P"),
        opened(
            prov,
            "EXTEND",
            FileFrame(
                "EX",
                FileOrganization(_INDEXED),
                AccessMode(_SEQ),
                PrimeKey(0, 2),
                0,
                True,
                False,
                0,
                2,
            ),
        ),
        prov._write_record("EX", "EF", "", "P"),
        prov._close_file("EX", "P"),
        opened(
            prov,
            "EXTEND",
            FileFrame(
                "NO",
                FileOrganization(_SEQ),
                AccessMode(_SEQ),
                PrimeKey(0, 0),
                0,
                False,
                False,
                0,
                2,
            ),
        ),
        opened(
            prov,
            "I-O",
            FileFrame(
                "NO",
                FileOrganization(_INDEXED),
                AccessMode(_DYNAMIC),
                PrimeKey(0, 2),
                0,
                False,
                False,
                0,
                2,
            ),
        ),
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
