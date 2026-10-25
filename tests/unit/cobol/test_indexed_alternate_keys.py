"""An indexed file with alternate record keys keeps one index per key: it reads and
positions by whichever key is the key of reference, keeps every index on WRITE, REWRITE
and DELETE, refuses a duplicate of a unique key, and reports a duplicate of a key that
allows them."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cobol_asg.file_enums import OpenMode
from interpreter.cobol.features import CobolFeature
from interpreter.record_io.access_result import AccessCondition, AccessResult
from interpreter.record_io.alternate_key import AlternateKey
from interpreter.record_io.file_drivers import IndexedDriver
from interpreter.record_io.prime_key import PrimeKey
from tests.covers import covers

_RL = 3
_PRIME = PrimeKey(0, 1)
_UNIQUE = AlternateKey(PrimeKey(1, 1), True)
_REPEATING = AlternateKey(PrimeKey(2, 1), False)
_UNIQUE_KEY = 1
_REPEATING_KEY = 2


def _opened(path: Path, mode: OpenMode) -> IndexedDriver:
    driver = IndexedDriver((_UNIQUE, _REPEATING))
    driver.open(path, mode, _RL, _PRIME)
    return driver


def _outcome(result: AccessResult) -> tuple[AccessCondition, bytes]:
    return result.condition, result.data or b""


def _walk(driver: IndexedDriver, count: int) -> list[tuple[AccessCondition, bytes]]:
    return [_outcome(driver.read_seq()) for _ in range(count)]


def _walk_from(
    driver: IndexedDriver, reference: int, count: int
) -> list[tuple[AccessCondition, bytes]]:
    driver.key_of_reference(reference)
    driver.start(b"A", ">=")
    return _walk(driver, count)


def _written(path: Path, records: Sequence[bytes]) -> list[AccessCondition]:
    driver = _opened(path, OpenMode.OUTPUT)
    conditions = [driver.write(record).condition for record in records]
    driver.close()
    return conditions


@covers(CobolFeature.START)
def test_reads_and_positions_by_the_key_of_reference(tmp_path: Path) -> None:
    path = tmp_path / "ix.dat"
    _written(path, [b"AZP", b"BYQ", b"CXR", b"DWS"])
    driver = _opened(path, OpenMode.INPUT)
    by_alternate = driver.key_of_reference(_UNIQUE_KEY).condition
    keyed = _outcome(driver.read_key(b"Y"))
    missing = driver.read_key(b"A").condition
    started = driver.start(b"X", ">").condition
    after = _walk(driver, 3)
    by_prime = _walk_from(driver, 0, 1)
    assert (by_alternate, keyed, missing, started, after, by_prime) == (
        AccessCondition.OK,
        (AccessCondition.OK, b"BYQ"),
        AccessCondition.NOT_FOUND,
        AccessCondition.OK,
        [
            (AccessCondition.OK, b"BYQ"),
            (AccessCondition.OK, b"AZP"),
            (AccessCondition.END_OF_FILE, b""),
        ],
        [(AccessCondition.OK, b"AZP")],
    )


@covers(CobolFeature.WRITE)
def test_duplicates_are_refused_or_reported_and_read_in_the_order_written(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ix.dat"
    conditions = _written(path, [b"AZP", b"BYQ", b"CXP", b"DYS", b"EWP"])
    driver = _opened(path, OpenMode.INPUT)
    driver.key_of_reference(_REPEATING_KEY)
    first = _outcome(driver.read_key(b"P"))
    started = driver.start(b"P", "=").condition
    run = _walk(driver, 5)
    assert (conditions, first, started, run) == (
        [
            AccessCondition.OK,
            AccessCondition.OK,
            AccessCondition.DUPLICATES_FOLLOW,
            AccessCondition.DUPLICATE_KEY,
            AccessCondition.DUPLICATES_FOLLOW,
        ],
        (AccessCondition.DUPLICATES_FOLLOW, b"AZP"),
        AccessCondition.OK,
        [
            (AccessCondition.DUPLICATES_FOLLOW, b"AZP"),
            (AccessCondition.DUPLICATES_FOLLOW, b"CXP"),
            (AccessCondition.OK, b"EWP"),
            (AccessCondition.OK, b"BYQ"),
            (AccessCondition.END_OF_FILE, b""),
        ],
    )


@covers(CobolFeature.REWRITE)
def test_rewrite_and_delete_keep_every_index(tmp_path: Path) -> None:
    path = tmp_path / "ix.dat"
    _written(path, [b"AZP", b"BYQ", b"CXR"])
    driver = _opened(path, OpenMode.IO)
    taken = driver.rewrite(b"AYP").condition
    moved = driver.rewrite(b"AVR").condition
    deleted = driver.delete(b"B").condition
    unique_order = _walk_from(driver, _UNIQUE_KEY, 3)
    repeating_order = _walk_from(driver, _REPEATING_KEY, 3)
    assert (taken, moved, deleted, unique_order, repeating_order) == (
        AccessCondition.DUPLICATE_KEY,
        AccessCondition.DUPLICATES_FOLLOW,
        AccessCondition.OK,
        [
            (AccessCondition.OK, b"AVR"),
            (AccessCondition.OK, b"CXR"),
            (AccessCondition.END_OF_FILE, b""),
        ],
        [
            (AccessCondition.DUPLICATES_FOLLOW, b"CXR"),
            (AccessCondition.OK, b"AVR"),
            (AccessCondition.END_OF_FILE, b""),
        ],
    )
