# pyright: standard
"""COBOL file organization drivers.

Three flat-file implementations covering SEQUENTIAL, INDEXED, and RELATIVE
file organizations. All use fixed-length records.
"""

from __future__ import annotations

import bisect
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.alternate_index import (
    AlternateIndex,
    IndexEntry,
    after,
    indexes_of,
)
from interpreter.cobol.alternate_key import AlternateKey
from interpreter.cobol.flagged_slot import FlaggedSlot
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.record_shape import RecordShape
from interpreter.cobol.relative_slot import RelativeSlot

logger = logging.getLogger(__name__)

_FLAGGED = FlaggedSlot()

# Open modes that permit a WRITE statement. A WRITE attempted on a file open
# in any other mode (e.g. INPUT) yields COBOL file status 48.
_WRITE_MODES = frozenset({OpenMode.OUTPUT, OpenMode.EXTEND, OpenMode.IO})


@runtime_checkable
class FileOrganizationDriver(Protocol):
    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key: PrimeKey,
    ) -> None: ...
    def close(self) -> None: ...
    def read_seq(self) -> AccessResult: ...
    def read_prev(self) -> AccessResult: ...
    def read_key(self, key: bytes) -> AccessResult: ...
    def start(self, key: bytes, relop: str) -> AccessResult: ...
    def key_of_reference(self, number: int) -> AccessResult: ...
    def write(self, data: bytes, key: bytes = b"") -> AccessResult: ...
    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult: ...
    def delete(self, key: bytes = b"") -> AccessResult: ...


def open_driver(
    path: Path, mode: OpenMode, shape: RecordShape
) -> FileOrganizationDriver:
    """Select and open the driver for a file organization. The one door
    every consumer (COBOL adapter, IDCAMS, …) uses to reach a dataset."""
    org = shape.organization
    if org == FileOrganization.INDEXED:
        drv: FileOrganizationDriver = IndexedDriver(shape.alternates)
    elif org == FileOrganization.RELATIVE:
        drv = RelativeDriver()
    else:
        drv = SequentialDriver()
    drv.open(path, mode, shape.record_length, shape.key)
    return drv


class SequentialDriver:
    """Flat file: concatenated fixed-length records."""

    def __init__(self) -> None:
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._last_pos = 0
        self._mode = OpenMode.INPUT

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key: PrimeKey,
    ) -> None:
        self._rl = record_length
        self._mode = mode
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        elif mode == OpenMode.EXTEND:
            self._fh = open(path, "a+b")
        elif mode == OpenMode.IO:
            self._fh = open(path, "r+b")
        else:
            self._fh = open(path, "rb")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def read_seq(self) -> AccessResult:
        assert self._fh is not None
        self._last_pos = self._fh.tell()
        data = self._fh.read(self._rl)
        if not data:
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        return AccessResult(condition=AccessCondition.OK, data=data.ljust(self._rl))

    def read_prev(self) -> AccessResult:
        raise NotImplementedError("sequential files do not support READ PREVIOUS")

    def read_key(self, key: bytes) -> AccessResult:
        return AccessResult(condition=AccessCondition.NOT_FOUND)

    def start(self, key: bytes, relop: str) -> AccessResult:
        return AccessResult(condition=AccessCondition.OK)

    def key_of_reference(self, number: int) -> AccessResult:
        return AccessResult(condition=AccessCondition.OK)

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return AccessResult(condition=AccessCondition.WRITE_NOT_PERMITTED)
        self._fh.seek(0, 2)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return AccessResult(condition=AccessCondition.OK)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        self._fh.seek(self._last_pos)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return AccessResult(condition=AccessCondition.OK)

    def delete(self, key: bytes = b"") -> AccessResult:
        return AccessResult(condition=AccessCondition.OK)


class IndexedDriver:
    """Flat file of fixed-length records kept sorted by prime key, with an index per
    alternate record key built when the file opens; reads follow the key of reference.

    Binary search for O(log n) keyed reads; insert/delete shift the tail.
    """

    def __init__(self, alternates: Sequence[AlternateKey] = ()) -> None:
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._koff = 0
        self._klen = 0
        self._cursor = 0  # byte offset for sequential scan
        self._last_pos = 0  # byte offset of last-read record
        self._mode = OpenMode.INPUT
        self._alternates = tuple(alternates)
        self._indexes: tuple[AlternateIndex, ...] = ()
        self._stored, self._reference = 0, 0
        self._place: IndexEntry = (b"", 0, b"")

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key: PrimeKey,
    ) -> None:
        self._rl, self._koff, self._klen = record_length, key.offset, key.length
        self._cursor = 0
        self._mode = mode
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        elif mode in (OpenMode.IO, OpenMode.EXTEND):
            self._fh = open(path, "r+b")
        else:
            self._fh = open(path, "rb")
        self._index_records()

    def _index_records(self) -> None:
        records = [self._rec_at(slot) for slot in range(self._count())]
        self._indexes = indexes_of(
            self._alternates, [(record, self._prime(record)) for record in records]
        )
        self._stored = len(records)
        self._reference = 0

    def _prime(self, record: bytes) -> bytes:
        return record[self._koff : self._koff + self._klen]

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def key_of_reference(self, number: int) -> AccessResult:
        self._reference = number
        return AccessResult(condition=AccessCondition.OK)

    def _index(self) -> AlternateIndex:
        return self._indexes[self._reference - 1]

    def _by_alternate(self) -> bool:
        return self._reference > 0

    def _alternate_record(self, slot: int) -> AccessResult:
        index = self._index()
        entry = index.entries[slot]
        self._place = after(entry)
        found, _ = self._find(entry[2])
        self._last_pos = found * self._rl
        condition = (
            AccessCondition.DUPLICATES_FOLLOW
            if index.follows(slot)
            else AccessCondition.OK
        )
        return AccessResult(condition=condition, data=self._rec_at(found))

    def _read_alternate_seq(self) -> AccessResult:
        slot = self._index().next_from(self._place)
        if slot >= len(self._index().entries):
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        return self._alternate_record(slot)

    def _read_alternate_key(self, key: bytes) -> AccessResult:
        slot = self._index().first_leading(key, False)
        if not self._index().holds(key):
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        return self._alternate_record(slot)

    def _start_alternate(self, key: bytes, relop: str) -> AccessResult:
        index = self._index()
        slot = index.first_leading(key, relop == ">")
        within = slot < len(index.entries)
        found = within and (
            relop not in ("=", "==") or index.entries[slot][0][: len(key)] == key
        )
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._place = index.entries[slot]
        return AccessResult(condition=AccessCondition.OK)

    def _store(self, record: bytes) -> None:
        prime = self._prime(record)
        self._indexes = tuple(
            index.stored(record, self._stored, prime) for index in self._indexes
        )
        self._stored = self._stored + 1

    def _unstore(self, prime: bytes) -> None:
        self._indexes = tuple(index.without(prime) for index in self._indexes)

    def _duplicate(self, found: bool, record: bytes) -> bool:
        return found or self._refused(record, self._indexes)

    def _refused(self, record: bytes, changed: Sequence[AlternateIndex]) -> bool:
        return any(index.refuses(index.value_of(record)) for index in changed)

    def _stored_condition(
        self, record: bytes, changed: Sequence[AlternateIndex]
    ) -> AccessCondition:
        repeats = any(index.repeats(index.value_of(record)) for index in changed)
        return AccessCondition.DUPLICATES_FOLLOW if repeats else AccessCondition.OK

    def _count(self) -> int:
        assert self._fh is not None
        pos = self._fh.tell()
        self._fh.seek(0, 2)
        n = self._fh.tell() // self._rl
        self._fh.seek(pos)
        return n

    def _key_at(self, slot: int) -> bytes:
        assert self._fh is not None
        self._fh.seek(slot * self._rl + self._koff)
        return self._fh.read(self._klen)

    def _rec_at(self, slot: int) -> bytes:
        assert self._fh is not None
        self._fh.seek(slot * self._rl)
        return self._fh.read(self._rl)

    def _find(self, key: bytes) -> tuple[int, bool]:
        lo, hi = 0, self._count()
        while lo < hi:
            mid = (lo + hi) // 2
            k = self._key_at(mid)
            if k < key:
                lo = mid + 1
            elif k > key:
                hi = mid
            else:
                return mid, True
        return lo, False

    def _shifted_cursor(self, slot: int, shift: int) -> int:
        return self._cursor + shift if slot * self._rl < self._cursor else self._cursor

    def read_seq(self) -> AccessResult:
        if self._by_alternate():
            return self._read_alternate_seq()
        assert self._fh is not None
        n = self._count()
        if self._cursor >= n * self._rl:
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        self._last_pos = self._cursor
        self._fh.seek(self._cursor)
        data = self._fh.read(self._rl)
        self._cursor += self._rl
        return AccessResult(condition=AccessCondition.OK, data=data.ljust(self._rl))

    def read_prev(self) -> AccessResult:
        if self._by_alternate():
            raise NotImplementedError("READ PREVIOUS follows the prime key only")
        assert self._fh is not None
        # Mirror of read_seq: retreat one record and read it. The cursor points
        # one record past the last forward read, so the first READPREV after a
        # READNEXT re-reads that record (CICS browse reversal). At BOF -> END_OF_FILE.
        if self._cursor < self._rl:
            return AccessResult(condition=AccessCondition.END_OF_FILE)
        self._cursor -= self._rl
        self._last_pos = self._cursor
        self._fh.seek(self._cursor)
        data = self._fh.read(self._rl)
        return AccessResult(condition=AccessCondition.OK, data=data.ljust(self._rl))

    def read_key(self, key: bytes) -> AccessResult:
        if self._by_alternate():
            return self._read_alternate_key(key)
        slot, found = self._find(key)
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._last_pos = slot * self._rl
        self._cursor = self._last_pos + self._rl
        return AccessResult(condition=AccessCondition.OK, data=self._rec_at(slot))

    def _leading(self, key: bytes) -> Callable[[int], bytes]:
        return lambda slot: self._key_at(slot)[: len(key)]

    def _start_slot(self, key: bytes, relop: str) -> tuple[int, bool]:
        slots = range(self._count())
        leading = self._leading(key)
        if relop == ">":
            slot = bisect.bisect_right(slots, key, key=leading)
            return slot, slot < len(slots)
        slot = bisect.bisect_left(slots, key, key=leading)
        exists = slot < len(slots)
        return slot, exists and (relop not in ("=", "==") or leading(slot) == key)

    def start(self, key: bytes, relop: str) -> AccessResult:
        if self._by_alternate():
            return self._start_alternate(key, relop)
        return self._start_prime(key, relop)

    def _start_prime(self, key: bytes, relop: str) -> AccessResult:
        slot, found = self._start_slot(key, relop)
        # Position the cursor at the GTEQ slot even when it is past end-of-file
        # (slot == n): CICS seek-last browse (STARTBR past all keys, then
        # READPREV) needs the cursor at EOF to walk back. The NOT_FOUND
        # condition (COBOL START INVALID KEY) is unchanged.
        if found or relop not in ("=", "==", ">"):
            self._cursor = slot * self._rl
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        return AccessResult(condition=AccessCondition.OK)

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return AccessResult(condition=AccessCondition.WRITE_NOT_PERMITTED)
        if not key:
            key = data[self._koff : self._koff + self._klen]
        slot, found = self._find(key)
        rec = data[: self._rl].ljust(self._rl)
        if self._duplicate(found, rec):
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        condition = self._stored_condition(rec, self._indexes)
        n = self._count()
        # Extend file by one record
        self._fh.seek(0, 2)
        self._fh.write(b"\x00" * self._rl)
        # Shift tail forward
        for i in range(n, slot, -1):
            src = self._rec_at(i - 1)
            self._fh.seek(i * self._rl)
            self._fh.write(src)
        self._fh.seek(slot * self._rl)
        self._fh.write(rec)
        self._cursor = self._shifted_cursor(slot, self._rl)
        self._store(rec)
        return AccessResult(condition=condition)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if not key:
            key = data[self._koff : self._koff + self._klen]
        slot, found = self._find(key)
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        rec = data[: self._rl].ljust(self._rl)
        return self._replaced(
            self._fh, slot, rec, self._changed(self._rec_at(slot), rec)
        )

    def _changed(self, before: bytes, record: bytes) -> tuple[AlternateIndex, ...]:
        return tuple(
            index.without(self._prime(before))
            for index in self._indexes
            if index.value_of(before) != index.value_of(record)
        )

    def _replaced(
        self,
        fh: BinaryIO,
        slot: int,
        record: bytes,
        changed: Sequence[AlternateIndex],
    ) -> AccessResult:
        if self._refused(record, changed):
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        condition = self._stored_condition(record, changed)
        fh.seek(slot * self._rl)
        fh.write(record)
        self._restore(record, {index.key for index in changed})
        return AccessResult(condition=condition)

    def _restore(self, record: bytes, moved: set[AlternateKey]) -> None:
        prime = self._prime(record)
        self._indexes = tuple(
            (
                index.without(prime).stored(record, self._stored, prime)
                if index.key in moved
                else index
            )
            for index in self._indexes
        )
        self._stored = self._stored + 1

    def delete(self, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if not key:
            slot = self._last_pos // self._rl
        else:
            s, found = self._find(key)
            if not found:
                return AccessResult(condition=AccessCondition.NOT_FOUND)
            slot = s
        self._unstore(self._prime(self._rec_at(slot)))
        self._remove_slot(slot)
        return AccessResult(condition=AccessCondition.OK)

    def _remove_slot(self, slot: int) -> None:
        assert self._fh is not None
        n = self._count()
        tail = [self._rec_at(i) for i in range(slot + 1, n)]
        self._fh.seek(slot * self._rl)
        self._fh.write(b"".join(tail))
        self._fh.truncate((n - 1) * self._rl)
        self._cursor = self._shifted_cursor(slot, -self._rl)


class RelativeDriver:
    """Flat file of fixed-size slots, one per relative record number; how a
    slot holds its record is the injected RelativeSlot's choice.
    Record number passed as 4-byte big-endian key bytes.
    """

    def __init__(self, slot: RelativeSlot = _FLAGGED) -> None:
        self._format = slot
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._slot = 0
        self._cursor = 0  # current slot index for sequential read
        self._last_slot = 0
        self._mode = OpenMode.INPUT

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key: PrimeKey,
    ) -> None:
        self._rl = record_length
        self._slot = self._format.size(record_length)
        self._cursor = 0
        self._mode = mode
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        elif mode in (OpenMode.IO, OpenMode.EXTEND):
            self._fh = open(path, "r+b")
        else:
            self._fh = open(path, "rb")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _total_slots(self) -> int:
        assert self._fh is not None
        pos = self._fh.tell()
        self._fh.seek(0, 2)
        n = self._fh.tell() // self._slot
        self._fh.seek(pos)
        return n

    def _n(self, key: bytes) -> int:
        return int.from_bytes(key[:4], "big")

    def _pos(self, n: int) -> int:
        return (n - 1) * self._slot

    def _record_at(self, n: int) -> tuple[bytes, ...]:
        assert self._fh is not None
        self._fh.seek(self._pos(n))
        return self._format.record(self._fh.read(self._slot))

    def read_key(self, key: bytes) -> AccessResult:
        n = self._n(key)
        found = self._record_at(n) if n >= 1 else ()
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._last_slot = n
        return AccessResult(
            condition=AccessCondition.OK, data=found[0], record_number=n
        )

    def read_seq(self) -> AccessResult:
        total = self._total_slots()
        while self._cursor < total:
            self._cursor += 1
            found = self._record_at(self._cursor)
            if found:
                self._last_slot = self._cursor
                return AccessResult(
                    condition=AccessCondition.OK,
                    data=found[0],
                    record_number=self._cursor,
                )
        return AccessResult(condition=AccessCondition.END_OF_FILE)

    def read_prev(self) -> AccessResult:
        # Mirror of read_seq: scan backward from one slot before the cursor,
        # skipping empty slots. The cursor sits one slot past the last forward
        # read, so the first READPREV after a READNEXT re-reads it (browse
        # reversal). Past the first active slot -> END_OF_FILE.
        while self._cursor > 0:
            found = self._record_at(self._cursor)
            self._cursor -= 1
            if found:
                self._last_slot = self._cursor + 1
                return AccessResult(condition=AccessCondition.OK, data=found[0])
        return AccessResult(condition=AccessCondition.END_OF_FILE)

    def _first_record_from(self, n: int) -> int:
        slots = range(max(n, 1), self._total_slots() + 1)
        return next((m for m in slots if self._record_at(m)), 0)

    def key_of_reference(self, number: int) -> AccessResult:
        return AccessResult(condition=AccessCondition.OK)

    def start(self, key: bytes, relop: str) -> AccessResult:
        n = self._n(key)
        found = self._first_record_from(n + 1 if relop == ">" else n)
        missing = not found or (relop in ("=", "==") and found != n)
        if missing:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._cursor = found - 1
        return AccessResult(condition=AccessCondition.OK)

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return AccessResult(condition=AccessCondition.WRITE_NOT_PERMITTED)
        n = self._n(key) if key else self._total_slots() + 1
        if n < 1:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        total = self._total_slots()
        if n > total:
            self._fh.seek(0, 2)
            self._fh.write(b"\x00" * self._slot * (n - total))
        if self._record_at(n):
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        self._fh.seek(self._pos(n))
        self._fh.write(self._format.packed(data, self._rl))
        return AccessResult(condition=AccessCondition.OK, record_number=n)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        if n < 1 or not self._record_at(n):
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._fh.seek(self._pos(n))
        self._fh.write(self._format.packed(data, self._rl))
        return AccessResult(condition=AccessCondition.OK)

    def delete(self, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        self._fh.seek(self._pos(n))
        self._fh.write(self._format.vacant())
        return AccessResult(condition=AccessCondition.OK)
