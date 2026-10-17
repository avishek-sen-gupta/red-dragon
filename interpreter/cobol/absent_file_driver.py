"""The driver of an unavailable optional input file: it holds no records."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import FileOrganizationDriver

_END = AccessResult(AccessCondition.END_OF_FILE)
_NOT_FOUND = AccessResult(AccessCondition.NOT_FOUND)
_NOT_PERMITTED = AccessResult(AccessCondition.WRITE_NOT_PERMITTED)


class AbsentFileDriver(FileOrganizationDriver):
    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> None:
        return

    def close(self) -> None:
        return

    def read_seq(self) -> AccessResult:
        return _END

    def read_prev(self) -> AccessResult:
        return _END

    def read_key(self, key: bytes) -> AccessResult:
        return _NOT_FOUND

    def start(self, key: bytes, relop: str) -> AccessResult:
        return _NOT_FOUND

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        return _NOT_PERMITTED

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        return _NOT_PERMITTED

    def delete(self, key: bytes = b"") -> AccessResult:
        return _NOT_PERMITTED
