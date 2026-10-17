"""An open COBOL file: its driver, open mode, frame and the prime key of its last
record read or written."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import FileOrganizationDriver
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.file_logic_status import FileLogicStatus

_RELATIVE_KEY_BYTES = 4


def _permitted_unless(refused: bool, status: FileLogicStatus) -> FileLogicStatus:
    return status if refused else FileLogicStatus.PERMITTED


@dataclass(frozen=True)
class OpenFile:
    driver: FileOrganizationDriver
    mode: OpenMode
    attributes: FileFrame
    last_key: bytes = b""

    def _indexed_in_sequence(self) -> bool:
        return (
            self.attributes.organization is FileOrganization.INDEXED
            and self.attributes.access is AccessMode.SEQUENTIAL
        )

    def permitted(self) -> FileLogicStatus:
        return FileLogicStatus.PERMITTED

    def _out_of_sequence(self, record: bytes) -> bool:
        key = self.attributes.prime_key.of(record)
        return self._indexed_in_sequence() and key < self.last_key

    def write_check(self, record: bytes) -> FileLogicStatus:
        return _permitted_unless(
            self._out_of_sequence(record), FileLogicStatus.SEQUENCE_ERROR
        )

    def rewrite_check(self, record: bytes) -> FileLogicStatus:
        return _permitted_unless(
            self._indexed_in_sequence()
            and self.attributes.prime_key.of(record) != self.last_key,
            FileLogicStatus.SEQUENCE_ERROR,
        )

    def key_bytes(self, key: str) -> bytes:
        if not key:
            return b""
        if self.attributes.organization is FileOrganization.RELATIVE:
            return int(key).to_bytes(_RELATIVE_KEY_BYTES, "big")
        return key.encode("latin-1")

    def after_read(self, result: AccessResult) -> OpenFile:
        return replace(self, last_key=self.attributes.prime_key.of(result.data or b""))

    def after_write(self, record: bytes, result: AccessResult) -> OpenFile:
        written = result.condition is AccessCondition.OK
        return replace(
            self,
            last_key=self.attributes.prime_key.of(record) if written else self.last_key,
        )

    def after_other(self, result: AccessResult) -> OpenFile:
        return self
