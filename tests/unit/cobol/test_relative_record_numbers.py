"""A relative file is addressed by relative record number, given and returned as text."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.io_provider import IOResult
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers
from tests.unit.cobol.declared_files import opened

_REL = "RELATIVE"


def _seen(result: IOResult) -> tuple[str, str, int]:
    return (result.status, result.data or "", result.record_number)


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_keyed_verbs_address_the_record_number_they_are_given(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    opened(
        prov,
        "OUTPUT",
        FileFrame(
            "F",
            FileOrganization(_REL),
            AccessMode("DYNAMIC"),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            3,
        ),
    )
    writes = [
        prov._write_record("F", "ONE", "1", "P").status,
        prov._write_record("F", "TWO", "0003", "P").status,
        prov._write_record("F", "DUP", "3", "P").status,
        prov._write_record("F", "NIL", "0", "P").status,
    ]
    prov._close_file("F", "P")
    opened(
        prov,
        "I-O",
        FileFrame(
            "F",
            FileOrganization(_REL),
            AccessMode("DYNAMIC"),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            3,
        ),
    )
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
    opened(
        prov,
        "OUTPUT",
        FileFrame(
            "F",
            FileOrganization(_REL),
            AccessMode("SEQUENTIAL"),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            3,
        ),
    )
    written = [prov._write_record("F", rec, "", "P").record_number for rec in "AB"]
    prov._close_file("F", "P")
    opened(
        prov,
        "EXTEND",
        FileFrame(
            "F",
            FileOrganization(_REL),
            AccessMode("SEQUENTIAL"),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            3,
        ),
    )
    extended = prov._write_record("F", "C", "", "P").record_number
    prov._close_file("F", "P")
    opened(
        prov,
        "INPUT",
        FileFrame(
            "F",
            FileOrganization(_REL),
            AccessMode("SEQUENTIAL"),
            PrimeKey(0, 0),
            0,
            False,
            False,
            0,
            3,
        ),
    )
    read = [_seen(prov._read_record("F", "", "P")) for _ in range(4)]
    assert (written, extended, read) == (
        [1, 2],
        3,
        [("00", "A  ", 1), ("00", "B  ", 2), ("00", "C  ", 3), ("10", "", 0)],
    )
