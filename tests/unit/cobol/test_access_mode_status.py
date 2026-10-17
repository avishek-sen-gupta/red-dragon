"""RealFileIOProvider reports the I-O statuses that depend on a file's ACCESS MODE
and on its RELATIVE KEY's size: 21, 43 on a keyed file, and 14."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

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
    prov._open_file(
        "IX", "OUTPUT", 4, _INDEXED, 1, 2, _SEQUENTIAL, 0, False, False, "P"
    )
    writes = [
        prov._write_record("IX", record, "", "P").status
        for record in ("A10A", "B20B", "C15C", "D20D", "E30E")
    ]
    prov._close_file("IX", "P")
    prov._open_file("IX", "I-O", 4, _INDEXED, 1, 2, _SEQUENTIAL, 0, False, False, "P")
    updates = [
        prov._rewrite_record("IX", "X10X", "", "P").status,
        prov._read_record("IX", "", "P").status,
        prov._rewrite_record("IX", "X20X", "", "P").status,
        prov._delete_record("IX", "", "P").status,
        prov._read_record("IX", "", "P").status,
        prov._rewrite_record("IX", "Y20Y", "", "P").status,
    ]
    prov._close_file("IX", "P")
    prov._open_file("IX", "I-O", 4, _INDEXED, 1, 2, _RANDOM, 0, False, False, "P")
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
    prov._open_file(
        "RL", "OUTPUT", 1, _RELATIVE, 0, 0, _SEQUENTIAL, 0, False, False, "P"
    )
    [prov._write_record("RL", record, "", "P") for record in "ABCDEFGHIJK"]
    prov._close_file("RL", "P")
    prov._open_file(
        "RL", "INPUT", 1, _RELATIVE, 0, 0, _SEQUENTIAL, 1, False, False, "P"
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
