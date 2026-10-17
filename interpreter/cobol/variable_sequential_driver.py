"""A sequential file of variable-length records, each behind a 4-byte record
descriptor word: its length with the descriptor, big-endian, then 2 reserved bytes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO, Literal

from cobol_asg.file_enums import OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import FileOrganizationDriver

_RDW = 4
_FILE_MODES: Mapping[OpenMode, Literal["rb", "w+b", "a+b", "r+b"]] = {
    OpenMode.INPUT: "rb",
    OpenMode.OUTPUT: "w+b",
    OpenMode.EXTEND: "a+b",
    OpenMode.IO: "r+b",
}
_WRITE_MODES = frozenset({OpenMode.OUTPUT, OpenMode.EXTEND})


def _described(record: bytes) -> bytes:
    return (len(record) + _RDW).to_bytes(2, "big") + bytes(2) + record


class VariableSequentialDriver(FileOrganizationDriver):
    def __init__(self) -> None:
        self._handles: tuple[BinaryIO, ...] = ()
        self._mode = OpenMode.INPUT
        self._maximum = 0
        self._last = 0

    def _handle(self) -> BinaryIO:
        return self._handles[0]

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> None:
        self._handles = (open(path, _FILE_MODES[mode]),)  # noqa: SIM115
        self._mode = mode
        self._maximum = record_length

    def close(self) -> None:
        [handle.close() for handle in self._handles]
        self._handles = ()

    def read_seq(self) -> AccessResult:
        self._last = self._handle().tell()
        rdw = self._handle().read(_RDW)
        if not rdw:
            return AccessResult(AccessCondition.END_OF_FILE)
        length = int.from_bytes(rdw[:2], "big") - _RDW
        return AccessResult(AccessCondition.OK, self._handle().read(length))

    def read_prev(self) -> AccessResult:
        raise NotImplementedError("sequential files do not support READ PREVIOUS")

    def read_key(self, key: bytes) -> AccessResult:
        return AccessResult(AccessCondition.NOT_FOUND)

    def start(self, key: bytes, relop: str) -> AccessResult:
        return AccessResult(AccessCondition.OK)

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        if self._mode not in _WRITE_MODES:
            return AccessResult(AccessCondition.WRITE_NOT_PERMITTED)
        self._handle().seek(0, 2)
        self._handle().write(_described(data[: self._maximum]))
        return AccessResult(AccessCondition.OK)

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        end = self._handle().tell()
        if end - self._last != len(data) + _RDW:
            return AccessResult(AccessCondition.BOUNDARY_VIOLATION)
        self._handle().seek(self._last)
        self._handle().write(_described(data))
        return AccessResult(AccessCondition.OK)

    def delete(self, key: bytes = b"") -> AccessResult:
        return AccessResult(AccessCondition.OK)
