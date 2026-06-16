# pyright: standard
"""COBOL file organization drivers.

Three flat-file implementations covering SEQUENTIAL, INDEXED, and RELATIVE
file organizations. All use fixed-length records.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from interpreter.cobol.file_enums import OpenMode
from interpreter.cobol.io_provider import IOResult

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
    def read_seq(self) -> IOResult: ...
    def read_key(self, key: bytes) -> IOResult: ...
    def start(self, key: bytes, relop: str) -> IOResult: ...
    def write(self, data: bytes, key: bytes = b"") -> IOResult: ...
    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult: ...
    def delete(self, key: bytes = b"") -> IOResult: ...


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

    def read_seq(self) -> IOResult:
        assert self._fh is not None
        self._last_pos = self._fh.tell()
        data = self._fh.read(self._rl)
        if not data:
            return IOResult("10", None)
        return IOResult("00", data.ljust(self._rl).decode("latin-1"))

    def read_key(self, key: bytes) -> IOResult:
        return IOResult("23", None)

    def start(self, key: bytes, relop: str) -> IOResult:
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return IOResult("48", None)
        self._fh.seek(0, 2)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        self._fh.seek(self._last_pos)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        return IOResult("00", None)


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
        elif mode == OpenMode.IO:
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

    def read_seq(self) -> IOResult:
        assert self._fh is not None
        n = self._count()
        if self._cursor >= n * self._rl:
            return IOResult("10", None)
        self._last_pos = self._cursor
        self._fh.seek(self._cursor)
        data = self._fh.read(self._rl)
        self._cursor += self._rl
        return IOResult("00", data.ljust(self._rl).decode("latin-1"))

    def read_key(self, key: bytes) -> IOResult:
        slot, found = self._find(key)
        if not found:
            return IOResult("23", None)
        self._last_pos = slot * self._rl
        return IOResult("00", self._rec_at(slot).decode("latin-1"))

    def start(self, key: bytes, relop: str) -> IOResult:
        slot, found = self._find(key)
        n = self._count()
        if relop in ("=", "=="):
            if not found:
                return IOResult("23", None)
            self._cursor = slot * self._rl
        elif relop == ">":
            if found:
                slot += 1
            if slot >= n:
                return IOResult("23", None)
            self._cursor = slot * self._rl
        else:  # >= or anything else
            if slot >= n:
                return IOResult("23", None)
            self._cursor = slot * self._rl
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return IOResult("48", None)
        if not key:
            key = data[self._koff : self._koff + self._klen]
        slot, found = self._find(key)
        if found:
            return IOResult("22", None)
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
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if not key:
            key = data[self._koff : self._koff + self._klen]
        slot, found = self._find(key)
        if not found:
            return IOResult("23", None)
        self._fh.seek(slot * self._rl)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if not key:
            slot = self._last_pos // self._rl
        else:
            s, found = self._find(key)
            if not found:
                return IOResult("23", None)
            slot = s
        n = self._count()
        # Shift tail backward
        for i in range(slot, n - 1):
            src = self._rec_at(i + 1)
            self._fh.seek(i * self._rl)
            self._fh.write(src)
        self._fh.seek((n - 1) * self._rl)
        self._fh.truncate()
        return IOResult("00", None)


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
        elif mode == OpenMode.IO:
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

    def read_key(self, key: bytes) -> IOResult:
        assert self._fh is not None
        n = self._n(key)
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _EMPTY:
            return IOResult("23", None)
        data = self._fh.read(self._rl)
        self._last_slot = n
        return IOResult("00", data.decode("latin-1"))

    def read_seq(self) -> IOResult:
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
                return IOResult("00", data.decode("latin-1"))
        return IOResult("10", None)

    def start(self, key: bytes, relop: str) -> IOResult:
        n = self._n(key)
        self._cursor = n - 1
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if self._mode not in _WRITE_MODES:
            return IOResult("48", None)
        if key:
            n = self._n(key)
        else:
            # Sequential write: append to next slot
            n = self._total_slots() + 1
        # Ensure file is large enough
        total = self._total_slots()
        if n > total:
            self._fh.seek(0, 2)
            self._fh.write(b"\x00" * self._slot * (n - total))
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if flag == _ACTIVE:
            return IOResult("22", None)
        self._fh.seek(self._pos(n))
        self._fh.write(_ACTIVE)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        self._fh.seek(self._pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _EMPTY:
            return IOResult("23", None)
        self._fh.write(data[: self._rl].ljust(self._rl))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        n = self._n(key) if key else self._last_slot
        self._fh.seek(self._pos(n))
        self._fh.write(_EMPTY)
        return IOResult("00", None)
