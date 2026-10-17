"""An open COBOL file: its driver, open mode, organization, access mode, keys and
position indicator."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import FileOrganizationDriver
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_position import FilePosition

_READ_MODES = frozenset({OpenMode.INPUT, OpenMode.IO})
_SEQUENTIAL_WRITE_MODES = frozenset({OpenMode.OUTPUT, OpenMode.EXTEND})
_RELATIVE_OR_INDEXED_WRITE_MODES = frozenset(
    {OpenMode.OUTPUT, OpenMode.EXTEND, OpenMode.IO}
)
_RELATIVE_KEY_BYTES = 4
_READ_POSITIONS = {
    AccessCondition.OK: FilePosition.CURRENT_RECORD,
    AccessCondition.DUPLICATES_FOLLOW: FilePosition.CURRENT_RECORD,
    AccessCondition.END_OF_FILE: FilePosition.AT_END,
}


def _permitted_unless(refused: bool, status: FileLogicStatus) -> FileLogicStatus:
    return status if refused else FileLogicStatus.PERMITTED


@dataclass(frozen=True)
class OpenFile:
    driver: FileOrganizationDriver
    mode: OpenMode
    attributes: FileFrame
    position: FilePosition = FilePosition.NO_CURRENT_RECORD
    last_key: bytes = b""

    def _sequential(self) -> bool:
        return self.attributes.organization is FileOrganization.SEQUENTIAL

    def _sequential_access(self) -> bool:
        return self._sequential() or self.attributes.access is AccessMode.SEQUENTIAL

    def _indexed_in_sequence(self) -> bool:
        return (
            self.attributes.organization is FileOrganization.INDEXED
            and self.attributes.access is AccessMode.SEQUENTIAL
        )

    def _write_modes(self) -> frozenset[OpenMode]:
        return (
            _SEQUENTIAL_WRITE_MODES
            if self._sequential()
            else _RELATIVE_OR_INDEXED_WRITE_MODES
        )

    def _exceeds_relative_key(self, result: AccessResult) -> bool:
        digits = len(str(result.record_number))
        return 0 < self.attributes.relative_key_digits < digits

    def read_check(self, sequential_read: bool) -> FileLogicStatus:
        if self.mode not in _READ_MODES:
            return FileLogicStatus.READ_NOT_PERMITTED
        return _permitted_unless(
            sequential_read and self.position is FilePosition.AT_END,
            FileLogicStatus.NO_NEXT_RECORD,
        )

    def read_outcome(self, result: AccessResult) -> FileLogicStatus:
        return _permitted_unless(
            self._exceeds_relative_key(result),
            FileLogicStatus.RELATIVE_KEY_TOO_SMALL,
        )

    def start_check(self) -> FileLogicStatus:
        return _permitted_unless(
            self.mode not in _READ_MODES, FileLogicStatus.READ_NOT_PERMITTED
        )

    def _before_first_record(self, key: str) -> bool:
        relative = self.attributes.organization is FileOrganization.RELATIVE
        return relative and bool(key) and int(key) < 1

    def _outside_sizes(self, record: bytes) -> bool:
        attributes = self.attributes
        sizes = range(
            attributes.minimum_record_length, attributes.maximum_record_length + 1
        )
        return attributes.variable and len(record) not in sizes

    def _out_of_sequence(self, record: bytes) -> bool:
        key = self.attributes.prime_key.of(record)
        return self._indexed_in_sequence() and key < self.last_key

    def write_check(self, record: bytes, key: str) -> FileLogicStatus:
        refusals = (
            (self.mode not in self._write_modes(), FileLogicStatus.WRITE_NOT_PERMITTED),
            (self._outside_sizes(record), FileLogicStatus.RECORD_SIZE_VIOLATION),
            (self._before_first_record(key), FileLogicStatus.BOUNDARY_VIOLATION),
            (self._out_of_sequence(record), FileLogicStatus.SEQUENCE_ERROR),
        )
        return next(
            (status for refused, status in refusals if refused),
            FileLogicStatus.PERMITTED,
        )

    def _current_record_check(self) -> FileLogicStatus:
        if self.mode is not OpenMode.IO:
            return FileLogicStatus.UPDATE_NOT_PERMITTED
        return _permitted_unless(
            self._sequential_access()
            and self.position is not FilePosition.CURRENT_RECORD,
            FileLogicStatus.NO_CURRENT_RECORD,
        )

    def rewrite_check(self, record: bytes) -> FileLogicStatus:
        current = self._current_record_check()
        if current is not FileLogicStatus.PERMITTED:
            return current
        if self._outside_sizes(record):
            return FileLogicStatus.RECORD_SIZE_VIOLATION
        return _permitted_unless(
            self._indexed_in_sequence()
            and self.attributes.prime_key.of(record) != self.last_key,
            FileLogicStatus.SEQUENCE_ERROR,
        )

    def delete_check(self) -> FileLogicStatus:
        return self._current_record_check()

    def key_bytes(self, key: str) -> bytes:
        if not key:
            return b""
        if self.attributes.organization is FileOrganization.RELATIVE:
            return int(key).to_bytes(_RELATIVE_KEY_BYTES, "big")
        return key.encode("latin-1")

    def _read_position(self, result: AccessResult) -> FilePosition:
        if self._exceeds_relative_key(result):
            return FilePosition.AT_END
        return _READ_POSITIONS.get(result.condition, FilePosition.NO_CURRENT_RECORD)

    def after_read(self, result: AccessResult) -> OpenFile:
        return replace(
            self,
            position=self._read_position(result),
            last_key=self.attributes.prime_key.of(result.data or b""),
        )

    def after_write(self, record: bytes, result: AccessResult) -> OpenFile:
        written = result.condition is AccessCondition.OK
        return replace(
            self,
            position=FilePosition.NO_CURRENT_RECORD,
            last_key=self.attributes.prime_key.of(record) if written else self.last_key,
        )

    def after_refusal(self) -> OpenFile:
        if self.position is FilePosition.CURRENT_RECORD:
            return replace(self, position=FilePosition.NO_CURRENT_RECORD)
        return self

    def after_other(self, result: AccessResult) -> OpenFile:
        return replace(self, position=FilePosition.NO_CURRENT_RECORD)
