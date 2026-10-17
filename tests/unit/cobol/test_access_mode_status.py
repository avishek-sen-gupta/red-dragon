"""RealFileIOProvider reports the I-O statuses that depend on a file's ACCESS MODE
and on its RELATIVE KEY's size: 21, 43 on a keyed file, and 14."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers
from tests.unit.cobol.declared_files import opened

_INDEXED = "INDEXED"
_RELATIVE = "RELATIVE"
_SEQUENTIAL = "SEQUENTIAL"
_RANDOM = "RANDOM"


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
@covers(CobolFeature.DELETE_RECORD)
def test_sequential_access_to_an_indexed_file_follows_its_prime_key(
    tmp_path: Path,
) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    opened(
        prov,
        "OUTPUT",
        FileFrame(
            "IX",
            FileOrganization(_INDEXED),
            AccessMode(_SEQUENTIAL),
            PrimeKey(1, 2),
            0,
            False,
            False,
            0,
            4,
        ),
    )
    writes = [
        prov._write_record("IX", record, "", "P").status
        for record in ("A10A", "B20B", "C15C", "D20D", "E30E")
    ]
    prov._close_file("IX", "P")
    opened(
        prov,
        "I-O",
        FileFrame(
            "IX",
            FileOrganization(_INDEXED),
            AccessMode(_SEQUENTIAL),
            PrimeKey(1, 2),
            0,
            False,
            False,
            0,
            4,
        ),
    )
    updates = [
        prov._rewrite_record("IX", "X10X", "", "P").status,
        prov._read_record("IX", "", "P").status,
        prov._rewrite_record("IX", "X20X", "", "P").status,
        prov._delete_record("IX", "", "P").status,
        prov._read_record("IX", "", "P").status,
        prov._rewrite_record("IX", "Y20Y", "", "P").status,
    ]
    prov._close_file("IX", "P")
    opened(
        prov,
        "I-O",
        FileFrame(
            "IX",
            FileOrganization(_INDEXED),
            AccessMode(_RANDOM),
            PrimeKey(1, 2),
            0,
            False,
            False,
            0,
            4,
        ),
    )
    keyed = prov._rewrite_record("IX", "Z30Z", "", "P").status
    prov._close_file("IX", "P")
    assert (writes, updates, keyed, (tmp_path / "ix.dat").read_bytes()) == (
        ["00", "00", "21", "22", "00"],
        ["43", "00", "21", "43", "00", "00"],
        "00",
        b"A10AY20YZ30Z",
    )


@covers(CobolFeature.READ)
def test_a_sequential_read_past_the_relative_keys_size_is_status_14(
    tmp_path: Path,
) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    opened(
        prov,
        "OUTPUT",
        FileFrame(
            "RL",
            FileOrganization(_RELATIVE),
            AccessMode(_SEQUENTIAL),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            1,
        ),
    )
    [prov._write_record("RL", record, "", "P") for record in "ABCDEFGHIJK"]
    prov._close_file("RL", "P")
    opened(
        prov,
        "INPUT",
        FileFrame(
            "RL",
            FileOrganization(_RELATIVE),
            AccessMode(_SEQUENTIAL),
            PrimeKey(0, 0),
            1,
            False,
            False,
            0,
            1,
        ),
    )
    reads = [
        (result.status, result.data or "", result.record_number)
        for result in (prov._read_record("RL", "", "P") for _ in range(11))
    ]
    assert reads == [
        *(("00", chr(64 + n), n) for n in range(1, 10)),
        ("14", "", 0),
        ("46", "", 0),
    ]
