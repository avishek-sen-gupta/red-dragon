"""AlternateIndexDriver: a sorted base file read and written in alternate-key order."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.alternate_index_driver import open_alternate_index_driver
from interpreter.cobol.real_file_provider import to_ioresult

_BASE = (b"001BBBxx", b"002AAAyy", b"003AAAzz", b"004CCCww")


def _base(tmp_path: Path, records: tuple[bytes, ...] = _BASE) -> Path:
    path = tmp_path / "base"
    path.write_bytes(b"".join(records))
    return path


def _path(base: Path, mode: OpenMode, unique: bool = False):
    return open_alternate_index_driver(base, mode, 8, 0, 3, 3, 3, unique)


def _walk(read):
    return [
        (r.condition, r.data)
        for r in iter(read, AccessResult(condition=AccessCondition.END_OF_FILE))
    ]


def test_reads_and_browses_by_alternate_key_reporting_duplicates(tmp_path):
    drv = _path(_base(tmp_path), OpenMode.INPUT)
    point = drv.read_key(b"AAA")
    missing = drv.read_key(b"ZZZ")
    drv.start(b"AAA", ">=")
    forward = _walk(drv.read_seq)
    backward = _walk(drv.read_prev)
    drv.close()

    assert (point.condition, point.data, missing.condition, forward, backward) == (
        AccessCondition.DUPLICATES_FOLLOW,
        b"002AAAyy",
        AccessCondition.NOT_FOUND,
        [
            (AccessCondition.DUPLICATES_FOLLOW, b"002AAAyy"),
            (AccessCondition.OK, b"003AAAzz"),
            (AccessCondition.OK, b"001BBBxx"),
            (AccessCondition.OK, b"004CCCww"),
        ],
        [
            (AccessCondition.OK, b"004CCCww"),
            (AccessCondition.OK, b"001BBBxx"),
            (AccessCondition.DUPLICATES_FOLLOW, b"003AAAzz"),
            (AccessCondition.OK, b"002AAAyy"),
        ],
    )


def test_start_positions_by_relational_operator(tmp_path):
    drv = _path(_base(tmp_path), OpenMode.INPUT)
    equal = (drv.start(b"BBB", "=").condition, drv.read_seq().data)
    after = (drv.start(b"AAA", ">").condition, drv.read_seq().data)
    absent = drv.start(b"ABC", "=").condition
    past_end = drv.start(b"ZZZ", ">=").condition
    drv.close()

    assert equal == (AccessCondition.OK, b"001BBBxx")
    assert after == (AccessCondition.OK, b"001BBBxx")
    assert absent is AccessCondition.NOT_FOUND
    assert past_end is AccessCondition.NOT_FOUND


def test_writes_rewrites_and_deletes_through_the_path_land_in_the_base(tmp_path):
    base = _base(tmp_path)
    drv = _path(base, OpenMode.IO)
    wrote = drv.write(b"000AAAqq").condition
    rewrote = drv.rewrite(b"004AAAww").condition
    deleted = drv.delete(b"AAA").condition
    drv.start(b"", ">=")
    seen = [data for _, data in _walk(drv.read_seq)]
    drv.close()

    assert (wrote, rewrote, deleted, seen, base.read_bytes()) == (
        AccessCondition.OK,
        AccessCondition.OK,
        AccessCondition.DUPLICATES_FOLLOW,
        [b"002AAAyy", b"003AAAzz", b"004AAAww", b"001BBBxx"],
        b"001BBBxx002AAAyy003AAAzz004AAAww",
    )


def test_a_unique_alternate_key_rejects_a_repeat(tmp_path):
    drv = _path(_base(tmp_path, (b"001BBBxx", b"002AAAyy")), OpenMode.IO, unique=True)
    repeated = drv.write(b"003AAAzz").condition
    moved_onto = drv.rewrite(b"001AAAxx").condition
    drv.close()

    assert (repeated, moved_onto) == (
        AccessCondition.DUPLICATE_KEY,
        AccessCondition.DUPLICATE_KEY,
    )


def test_more_duplicates_follow_is_cobol_status_02():
    result = to_ioresult(AccessResult(AccessCondition.DUPLICATES_FOLLOW, b"x"))

    assert (result.status, result.data) == ("02", "x")
