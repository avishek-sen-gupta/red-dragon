from pathlib import Path

import pytest

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_drivers import (
    AlternateKeyDriver,
    open_alternate_key_driver,
)
from interpreter.cobol.file_enums import OpenMode
from tests.covers import covers, NotLanguageFeature

# 8-byte records. Primary key at offset 0 (file IS sorted by it: AAA<BBB<CCC).
# Alternate key at offset 3, length 2 — its values (xz, yw, ab) are NOT in
# sorted order, so only a linear scan (not binary search) can find them.
_RECS = [b"AAAxz123", b"BBByw456", b"CCCab789"]


def _seed(path: Path) -> None:
    path.write_bytes(b"".join(_RECS))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_finds_out_of_sort_order_key(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    # "ab" is the alt key of the LAST record, out of alt-key sort order.
    r = drv.read_key(b"ab")
    assert r.condition is AccessCondition.OK
    assert r.data == b"CCCab789"
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_finds_middle_record(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    r = drv.read_key(b"yw")
    assert r.condition is AccessCondition.OK
    assert r.data == b"BBByw456"
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_miss_is_not_found(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    assert drv.read_key(b"zz").condition is AccessCondition.NOT_FOUND
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_factory_returns_opened_alternate_key_driver(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    assert isinstance(drv, AlternateKeyDriver)
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unsupported_ops_raise(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    with pytest.raises(NotImplementedError):
        drv.read_seq()
    with pytest.raises(NotImplementedError):
        drv.start(b"AA", ">=")
    with pytest.raises(NotImplementedError):
        drv.write(b"AAAxz999")
    with pytest.raises(NotImplementedError):
        drv.rewrite(b"AAAxz999")
    with pytest.raises(NotImplementedError):
        drv.delete()
    drv.close()
