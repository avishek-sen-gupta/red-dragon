from pathlib import Path

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.record_io.file_drivers import (
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
    open_driver,
)
from interpreter.record_io.prime_key import PrimeKey
from interpreter.record_io.record_shape import RecordShape
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_open_driver_selects_by_org(tmp_path: Path):
    seq = open_driver(
        tmp_path / "s",
        OpenMode.OUTPUT,
        RecordShape(FileOrganization.SEQUENTIAL, 5, PrimeKey(0, 0)),
    )
    idx = open_driver(
        tmp_path / "i",
        OpenMode.OUTPUT,
        RecordShape(FileOrganization.INDEXED, 8, PrimeKey(0, 3)),
    )
    rel = open_driver(
        tmp_path / "r",
        OpenMode.OUTPUT,
        RecordShape(FileOrganization.RELATIVE, 8, PrimeKey(0, 0)),
    )
    assert isinstance(seq, SequentialDriver)
    assert isinstance(idx, IndexedDriver)
    assert isinstance(rel, RelativeDriver)
    for d in (seq, idx, rel):
        d.close()
