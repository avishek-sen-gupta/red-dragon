# pyright: standard
"""A fixed-length base file, sorted by its primary key, read and written in the order of an alternate key."""

from __future__ import annotations

import bisect
from pathlib import Path

from cobol_asg.file_enums import OpenMode
from interpreter.record_io.access_result import AccessCondition, AccessResult
from interpreter.record_io.alternate_key import AlternateKey
from interpreter.record_io.file_drivers import FileOrganizationDriver, IndexedDriver
from interpreter.record_io.prime_key import PrimeKey
from interpreter.record_io.record_shape import RecordShape

_WRITE_MODES = frozenset({OpenMode.OUTPUT, OpenMode.EXTEND, OpenMode.IO})
_Entry = tuple[bytes, bytes]


def _alternate(entry: _Entry) -> bytes:
    return entry[0]


class AlternateIndexDriver:
    """Reads by alternate key; duplicates in primary-key order; writes go to the base file."""

    def __init__(self, primary: PrimeKey, unique: bool) -> None:
        self._primary = primary
        self._poff = primary.offset
        self._plen = primary.length
        self._unique = unique
        self._base = IndexedDriver()
        self._view: list[_Entry] = []
        self._cursor = 0
        self._last = 0
        self._rl = self._koff = self._klen = 0
        self._mode = OpenMode.INPUT

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key: PrimeKey,
    ) -> None:
        self._rl, self._koff, self._klen, self._mode = (
            record_length,
            key.offset,
            key.length,
            mode,
        )
        data = b"" if mode == OpenMode.OUTPUT else path.read_bytes()
        self._view = sorted(
            self._entry(data[i : i + record_length])
            for i in range(0, len(data), record_length)
        )
        self._cursor = 0
        self._last = 0
        self._base.open(path, mode, record_length, self._primary)

    def close(self) -> None:
        self._base.close()

    def _entry(self, record: bytes) -> _Entry:
        return (
            record[self._koff : self._koff + self._klen],
            record[self._poff : self._poff + self._plen],
        )

    def _first(self, key: bytes) -> int:
        return bisect.bisect_left(self._view, key, key=_alternate)

    def _holds(self, slot: int, key: bytes) -> bool:
        return 0 <= slot < len(self._view) and self._view[slot][0] == key

    def _swap(self, gone: list[_Entry], added: list[_Entry]) -> None:
        self._view = sorted([e for e in self._view if e not in gone] + added)

    def _record(self, slot: int, follows: bool) -> AccessResult:
        self._last = slot
        found = self._base.read_key(self._view[slot][1])
        condition = AccessCondition.DUPLICATES_FOLLOW if follows else AccessCondition.OK
        return AccessResult(condition=condition, data=found.data)

    def read_key(self, key: bytes) -> AccessResult:
        slot = self._first(key)
        if not self._holds(slot, key):
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        return self._record(slot, self._holds(slot + 1, key))

    def _seek(self, slot: int, found: bool) -> AccessResult:
        self._cursor = slot if found else self._cursor
        return AccessResult(
            condition=AccessCondition.OK if found else AccessCondition.NOT_FOUND
        )

    def _start_equal(self, key: bytes) -> AccessResult:
        slot = self._first(key)
        return self._seek(slot, self._holds(slot, key))

    def _start_after(self, key: bytes) -> AccessResult:
        slot = bisect.bisect_right(self._view, key, key=_alternate)
        return self._seek(slot, slot < len(self._view))

    def _start_from(self, key: bytes) -> AccessResult:
        self._cursor = self._first(key)
        return AccessResult(
            condition=(
                AccessCondition.OK
                if self._cursor < len(self._view)
                else AccessCondition.NOT_FOUND
            )
        )

    def start(self, key: bytes, relop: str) -> AccessResult:
        starts = {
            "=": self._start_equal,
            "==": self._start_equal,
            ">": self._start_after,
        }
        return starts.get(relop, self._start_from)(key)

    def key_of_reference(self, number: int) -> AccessResult:
        return AccessResult(condition=AccessCondition.OK)

    def read_seq(self) -> AccessResult:
        if self._cursor >= len(self._view):
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        slot = self._cursor
        self._cursor += 1
        return self._record(slot, self._holds(slot + 1, self._view[slot][0]))

    def read_prev(self) -> AccessResult:
        if self._cursor < 1:
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        self._cursor -= 1
        slot = self._cursor
        return self._record(slot, self._holds(slot - 1, self._view[slot][0]))

    def _taken(self, key: bytes) -> bool:
        return self._unique and self._holds(self._first(key), key)

    def _indexed(self, entry: _Entry, result: AccessResult) -> AccessResult:
        if result.condition is AccessCondition.OK:
            self._swap([], [entry])
        return result

    def _insert(self, data: bytes) -> AccessResult:
        entry = self._entry(data[: self._rl].ljust(self._rl))
        if self._taken(entry[0]):
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        return self._indexed(entry, self._base.write(data))

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        if self._mode not in _WRITE_MODES:
            return AccessResult(condition=AccessCondition.WRITE_NOT_PERMITTED)
        return self._insert(data)

    def _replaced(
        self, before: _Entry, entry: _Entry, result: AccessResult
    ) -> AccessResult:
        if result.condition is AccessCondition.OK:
            self._swap([before], [entry])
        return result

    def _moved(self, before: _Entry, entry: _Entry, data: bytes) -> AccessResult:
        if before[0] != entry[0] and self._taken(entry[0]):
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        return self._replaced(before, entry, self._base.rewrite(data))

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        entry = self._entry(data[: self._rl].ljust(self._rl))
        old = self._base.read_key(entry[1])
        if old.condition is not AccessCondition.OK:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        return self._moved(self._entry(old.data or b""), entry, data)

    def _last_slot(self) -> int:
        return min(self._last, len(self._view))

    def _keyed_slot(self, key: bytes) -> int:
        slot = self._first(key)
        return slot if self._holds(slot, key) else len(self._view)

    def _target(self, key: bytes) -> int:
        return self._keyed_slot(key) if key else self._last_slot()

    def _removed(self, slot: int, follows: bool, result: AccessResult) -> AccessResult:
        if result.condition is not AccessCondition.OK:
            return result
        self._swap([self._view[slot]], [])
        self._cursor = self._cursor - int(self._cursor > slot)
        return AccessResult(
            condition=(
                AccessCondition.DUPLICATES_FOLLOW if follows else AccessCondition.OK
            )
        )

    def delete(self, key: bytes = b"") -> AccessResult:
        slot = self._target(key)
        if slot >= len(self._view):
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        entry = self._view[slot]
        return self._removed(
            slot, self._holds(slot + 1, entry[0]), self._base.delete(entry[1])
        )


def open_alternate_index_driver(
    path: Path, mode: OpenMode, shape: RecordShape, alternate: AlternateKey
) -> FileOrganizationDriver:
    """Open an AlternateIndexDriver over a base file sorted by its primary key."""
    drv = AlternateIndexDriver(shape.key, alternate.unique)
    drv.open(path, mode, shape.record_length, alternate.key)
    return drv
