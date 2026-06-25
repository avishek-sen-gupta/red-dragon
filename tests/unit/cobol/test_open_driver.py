from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.cobol.file_drivers import (
    open_driver,
    SequentialDriver,
    IndexedDriver,
    RelativeDriver,
)
from interpreter.cobol.file_enums import FileOrganization, OpenMode


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_open_driver_selects_by_org(tmp_path: Path):
    seq = open_driver(
        FileOrganization.SEQUENTIAL, tmp_path / "s", OpenMode.OUTPUT, 5, 0, 0
    )
    idx = open_driver(
        FileOrganization.INDEXED, tmp_path / "i", OpenMode.OUTPUT, 8, 0, 3
    )
    rel = open_driver(
        FileOrganization.RELATIVE, tmp_path / "r", OpenMode.OUTPUT, 8, 0, 0
    )
    assert isinstance(seq, SequentialDriver)
    assert isinstance(idx, IndexedDriver)
    assert isinstance(rel, RelativeDriver)
    for d in (seq, idx, rel):
        d.close()
