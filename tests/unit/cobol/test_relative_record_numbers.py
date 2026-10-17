"""A relative file is addressed by relative record number, given and returned as text."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import IOResult
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

_REL = "RELATIVE"


def _seen(result: IOResult) -> tuple[str, str, int]:
    return (result.status, result.data or "", result.record_number)


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_keyed_verbs_address_the_record_number_they_are_given(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    prov._open_file("F", "OUTPUT", 3, _REL, 0, 0, "DYNAMIC", 0, False, "P")
    writes = [
        prov._write_record("F", "ONE", "1", "P").status,
        prov._write_record("F", "TWO", "0003", "P").status,
        prov._write_record("F", "DUP", "3", "P").status,
        prov._write_record("F", "NIL", "0", "P").status,
    ]
    prov._close_file("F", "P")
    prov._open_file("F", "I-O", 3, _REL, 0, 0, "DYNAMIC", 0, False, "P")
    reads = [
        _seen(prov._read_record("F", "0", "P")),
        _seen(prov._read_record("F", "5", "P")),
        _seen(prov._read_record("F", "2", "P")),
        _seen(prov._read_record("F", "3", "P")),
    ]
    updates = [
        prov._rewrite_record("F", "NIL", "0", "P").status,
        prov._rewrite_record("F", "NEW", "1", "P").status,
        prov._delete_record("F", "3", "P").status,
    ]
    after = [_seen(prov._read_record("F", key, "P")) for key in ("1", "3")]
    assert (writes, reads, updates, after) == (
        ["00", "00", "22", "24"],
        [("23", "", 0), ("23", "", 0), ("23", "", 0), ("00", "TWO", 3)],
        ["23", "00", "00"],
        [("00", "NEW", 1), ("23", "", 0)],
    )


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_sequential_verbs_return_the_record_number_they_used(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    prov._open_file("F", "OUTPUT", 3, _REL, 0, 0, "SEQUENTIAL", 0, False, "P")
    written = [prov._write_record("F", rec, "", "P").record_number for rec in "AB"]
    prov._close_file("F", "P")
    prov._open_file("F", "EXTEND", 3, _REL, 0, 0, "SEQUENTIAL", 0, False, "P")
    extended = prov._write_record("F", "C", "", "P").record_number
    prov._close_file("F", "P")
    prov._open_file("F", "INPUT", 3, _REL, 0, 0, "SEQUENTIAL", 0, False, "P")
    read = [_seen(prov._read_record("F", "", "P")) for _ in range(4)]
    assert (written, extended, read) == (
        [1, 2],
        3,
        [("00", "A  ", 1), ("00", "B  ", 2), ("00", "C  ", 3), ("10", "", 0)],
    )
