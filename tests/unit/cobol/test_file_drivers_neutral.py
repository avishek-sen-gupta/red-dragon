# pyright: standard
"""Neutral AccessResult behaviour tests for COBOL file organization drivers."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_drivers import IndexedDriver, SequentialDriver
from interpreter.cobol.file_enums import OpenMode
from tests.covers import covers


@covers(CobolFeature.READ)
def test_sequential_read_past_end_is_end_of_file(tmp_path: Path) -> None:
    p = tmp_path / "f"
    p.write_bytes(b"AAAAA")  # one 5-byte record
    drv = SequentialDriver()
    drv.open(p, OpenMode.INPUT, 5, 0, 0)
    assert drv.read_seq().condition is AccessCondition.OK
    assert drv.read_seq().condition is AccessCondition.END_OF_FILE
    drv.close()


@covers(CobolFeature.READ)
def test_indexed_read_key_miss_is_not_found(tmp_path: Path) -> None:
    p = tmp_path / "k"
    drv = IndexedDriver()
    drv.open(p, OpenMode.OUTPUT, 8, 0, 3)  # 8-byte record, 3-byte key at offset 0
    drv.write(b"AAArec01")
    assert drv.read_key(b"AAA").condition is AccessCondition.OK
    assert drv.read_key(b"ZZZ").condition is AccessCondition.NOT_FOUND
    drv.close()


@covers(CobolFeature.WRITE)
def test_indexed_duplicate_write_is_duplicate_key(tmp_path: Path) -> None:
    p = tmp_path / "k2"
    drv = IndexedDriver()
    drv.open(p, OpenMode.OUTPUT, 8, 0, 3)
    assert drv.write(b"AAArec01").condition is AccessCondition.OK
    assert drv.write(b"AAArec02").condition is AccessCondition.DUPLICATE_KEY
    drv.close()
