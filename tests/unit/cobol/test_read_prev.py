from pathlib import Path

import pytest

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_drivers import (
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
)
from interpreter.cobol.file_enums import OpenMode
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_indexed_read_prev_backward_and_reversal(tmp_path: Path):
    # 3 x 8-byte records, sorted by the 3-byte key at offset 0.
    p = tmp_path / "ksds"
    p.write_bytes(b"AAA00001" + b"BBB00002" + b"CCC00003")
    drv = IndexedDriver()
    drv.open(p, OpenMode.INPUT, 8, 0, 3)
    assert drv.start(b"AAA", ">=").condition is AccessCondition.OK
    # forward
    assert drv.read_seq().data == b"AAA00001"
    assert drv.read_seq().data == b"BBB00002"
    # reversal: the first READPREV re-reads the last forward record (CICS semantics)
    assert drv.read_prev().data == b"BBB00002"
    # continue backward
    assert drv.read_prev().data == b"AAA00001"
    # beginning-of-file
    assert drv.read_prev().condition is AccessCondition.END_OF_FILE
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_relative_read_prev_backward_and_reversal(tmp_path: Path):
    # 2 active slots, record_length=4: [0xff | record] per slot.
    p = tmp_path / "rrds"
    p.write_bytes(b"\xff" + b"AAAA" + b"\xff" + b"BBBB")
    drv = RelativeDriver()
    drv.open(p, OpenMode.INPUT, 4, 0, 0)
    assert drv.read_seq().data == b"AAAA"
    assert drv.read_seq().data == b"BBBB"
    assert drv.read_prev().data == b"BBBB"  # reversal re-reads
    assert drv.read_prev().data == b"AAAA"
    assert drv.read_prev().condition is AccessCondition.END_OF_FILE
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_sequential_read_prev_raises(tmp_path: Path):
    p = tmp_path / "ps"
    p.write_bytes(b"AAAAA")
    drv = SequentialDriver()
    drv.open(p, OpenMode.INPUT, 5, 0, 0)
    with pytest.raises(NotImplementedError):
        drv.read_prev()
    drv.close()
