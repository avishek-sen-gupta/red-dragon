"""Variable-length records on disk: a sequential file holds each record behind a 4-byte
record descriptor word, a relative file holds fixed slots of 4 + maximum bytes with the
descriptor word at the slot's start."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cobol_asg.file_enums import OpenMode
from infrastructure.zos.access_methods.access_result import AccessCondition
from infrastructure.zos.access_methods.described_slot import DescribedSlot
from infrastructure.zos.access_methods.file_drivers import (
    FileOrganizationDriver,
    RelativeDriver,
)
from infrastructure.zos.access_methods.prime_key import PrimeKey
from infrastructure.zos.access_methods.variable_sequential_driver import (
    VariableSequentialDriver,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _written(
    driver: FileOrganizationDriver,
    path: Path,
    maximum: int,
    records: Sequence[tuple[bytes, bytes]],
) -> list[AccessCondition]:
    driver.open(path, OpenMode.OUTPUT, maximum, PrimeKey(0, 0))
    conditions = [driver.write(record, key).condition for record, key in records]
    driver.close()
    return conditions


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
@covers(CobolFeature.REWRITE)
def test_a_sequential_file_keeps_each_record_at_its_own_length(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v.dat"
    written = _written(
        VariableSequentialDriver(), path, 5, ((b"ABC", b""), (b"DEFGH", b""))
    )
    io = VariableSequentialDriver()
    io.open(path, OpenMode.IO, 5, PrimeKey(0, 0))
    updates = (
        io.read_seq().data,
        io.rewrite(b"ABCD").condition,
        io.rewrite(b"XYZ").condition,
        io.read_seq().data,
        io.read_seq().condition,
    )
    io.close()
    assert (written, *updates, path.read_bytes()) == (
        [AccessCondition.OK, AccessCondition.OK],
        b"ABC",
        AccessCondition.BOUNDARY_VIOLATION,
        AccessCondition.OK,
        b"DEFGH",
        AccessCondition.END_OF_FILE,
        b"\x00\x07\x00\x00XYZ\x00\x09\x00\x00DEFGH",
    )


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
@covers(CobolFeature.DELETE_RECORD)
def test_a_relative_file_keeps_each_records_length_in_its_slot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "r.dat"
    _written(
        RelativeDriver(DescribedSlot()),
        path,
        4,
        ((b"AB", (1).to_bytes(4, "big")), (b"CDEF", (3).to_bytes(4, "big"))),
    )
    io = RelativeDriver(DescribedSlot())
    io.open(path, OpenMode.IO, 4, PrimeKey(0, 0))
    reads = [io.read_seq().data, io.read_seq().data, io.read_seq().condition]
    keyed = [io.read_key((n).to_bytes(4, "big")).condition for n in (2, 3)]
    io.delete((1).to_bytes(4, "big"))
    io.close()
    assert (reads, keyed, path.read_bytes()) == (
        [b"AB", b"CDEF", AccessCondition.END_OF_FILE],
        [AccessCondition.NOT_FOUND, AccessCondition.OK],
        b"\x00\x00\x00\x00AB\x00\x00" + bytes(8) + b"\x00\x08\x00\x00CDEF",
    )
