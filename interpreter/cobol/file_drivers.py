# pyright: standard
"""COBOL file organization drivers.

Three flat-file implementations covering SEQUENTIAL, INDEXED, and RELATIVE
file organizations. All use fixed-length records.
"""

from __future__ import annotations

import bisect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult

logger = logging.getLogger(__name__)

_ACTIVE = b"\xff"
_EMPTY = b"\x00"

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
        key_offset: int,
        key_length: int,
    ) -> None: ...
    def close(self) -> None: ...
    def read_seq(self) -> AccessResult: ...
    def read_prev(self) -> AccessResult: ...
    def read_key(self, key: bytes) -> AccessResult: ...
    def start(self, key: bytes, relop: str) -> AccessResult: ...
    def write(self, data: bytes, key: bytes = b"") -> AccessResult: ...
    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult: ...
    def delete(self, key: bytes = b"") -> AccessResult: ...


def open_driver(
    org: FileOrganization,
    path: Path,
    mode: OpenMode,
    record_length: int,
    key_offset: int,
    key_length: int,
) -> FileOrganizationDriver:
    """Select and open the driver for a file organization. The one door
    every consumer (COBOL adapter, IDCAMS, …) uses to reach a dataset."""
    if org == FileOrganization.INDEXED:
        drv: FileOrganizationDriver = IndexedDriver()
    elif org == FileOrganization.RELATIVE:
        drv = RelativeDriver()
    else:
        drv = SequentialDriver()
    drv.open(path, mode, record_length, key_offset, key_length)
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
        key_offset: int,
        key_length: int,
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
    """Flat file of fixed-length records kept sorted by key.

    Binary search for O(log n) keyed reads; insert/delete shift the tail.
    """

    def __init__(self) -> None:
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._koff = 0
        self._klen = 0
        self._cursor = 0  # byte offset for sequential scan
        self._last_pos = 0  # byte offset of last-read record
        self._mode = OpenMode.INPUT

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> None:
        self._rl = record_length
        self._koff = key_offset
        self._klen = key_length
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
        slot, found = self._find(key)
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._last_pos = slot * self._rl
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
        if found:
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        n = self._count()
        rec = data[: self._rl].ljust(self._rl)
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
        return AccessResult(condition=AccessCondition.OK)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if not key:
            key = data[self._koff : self._koff + self._klen]
        slot, found = self._find(key)
        if not found:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._fh.seek(slot * self._rl)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return AccessResult(condition=AccessCondition.OK)

    def delete(self, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if not key:
            slot = self._last_pos // self._rl
        else:
            s, found = self._find(key)
            if not found:
                return AccessResult(condition=AccessCondition.NOT_FOUND)
            slot = s
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
    """Flat file: [1-byte flag | record_length bytes] per slot.

    flag 0xFF = active, 0x00 = empty.
    Record number passed as 4-byte big-endian key bytes.
    """

    def __init__(self) -> None:
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._slot = 0  # slot size = 1 + record_length
        self._cursor = 0  # current slot index for sequential read
        self._last_slot = 0
        self._mode = OpenMode.INPUT

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> None:
        self._rl = record_length
        self._slot = 1 + record_length
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

    def read_key(self, key: bytes) -> AccessResult:
        assert self._fh is not None
        n = self._n(key)
        if n < 1:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _EMPTY:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        data = self._fh.read(self._rl)
        self._last_slot = n
        return AccessResult(condition=AccessCondition.OK, data=data, record_number=n)

    def read_seq(self) -> AccessResult:
        assert self._fh is not None
        total = self._total_slots()
        while self._cursor < total:
            slot = self._cursor
            self._cursor += 1
            self._fh.seek(slot * self._slot)
            flag = self._fh.read(1)
            if flag == _ACTIVE:
                data = self._fh.read(self._rl)
                self._last_slot = slot + 1
                return AccessResult(
                    condition=AccessCondition.OK, data=data, record_number=slot + 1
                )
        return AccessResult(condition=AccessCondition.END_OF_FILE)

    def read_prev(self) -> AccessResult:
        assert self._fh is not None
        # Mirror of read_seq: scan backward from one slot before the cursor,
        # skipping empty slots. The cursor sits one slot past the last forward
        # read, so the first READPREV after a READNEXT re-reads it (browse
        # reversal). Past the first active slot -> END_OF_FILE.
        while self._cursor > 0:
            self._cursor -= 1
            slot = self._cursor
            self._fh.seek(slot * self._slot)
            flag = self._fh.read(1)
            if flag == _ACTIVE:
                data = self._fh.read(self._rl)
                self._last_slot = slot + 1
                return AccessResult(condition=AccessCondition.OK, data=data)
        return AccessResult(condition=AccessCondition.END_OF_FILE)

    def start(self, key: bytes, relop: str) -> AccessResult:
        n = self._n(key)
        self._cursor = n - 1
        return AccessResult(condition=AccessCondition.OK)

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return AccessResult(condition=AccessCondition.WRITE_NOT_PERMITTED)
        n = self._n(key) if key else self._total_slots() + 1
        if n < 1:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        # Ensure file is large enough
        total = self._total_slots()
        if n > total:
            self._fh.seek(0, 2)
            self._fh.write(b"\x00" * self._slot * (n - total))
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if flag == _ACTIVE:
            return AccessResult(condition=AccessCondition.DUPLICATE_KEY)
        self._fh.seek(self._pos(n))
        self._fh.write(_ACTIVE)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return AccessResult(condition=AccessCondition.OK, record_number=n)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        if n < 1:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _EMPTY:
            return AccessResult(condition=AccessCondition.NOT_FOUND)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return AccessResult(condition=AccessCondition.OK)

    def delete(self, key: bytes = b"") -> AccessResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        self._fh.seek(self._pos(n))
        self._fh.write(_EMPTY)
        return AccessResult(condition=AccessCondition.OK)
