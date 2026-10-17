"""An open COBOL file: its driver, open mode, organization and position indicator."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_drivers import FileOrganizationDriver
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
    organization: FileOrganization
    position: FilePosition = FilePosition.NO_CURRENT_RECORD

    def _sequential(self) -> bool:
        return self.organization is FileOrganization.SEQUENTIAL

    def _write_modes(self) -> frozenset[OpenMode]:
        return (
            _SEQUENTIAL_WRITE_MODES
            if self._sequential()
            else _RELATIVE_OR_INDEXED_WRITE_MODES
        )

    def read_check(self, sequential_read: bool) -> FileLogicStatus:
        if self.mode not in _READ_MODES:
            return FileLogicStatus.READ_NOT_PERMITTED
        return _permitted_unless(
            sequential_read and self.position is FilePosition.AT_END,
            FileLogicStatus.NO_NEXT_RECORD,
        )

    def start_check(self) -> FileLogicStatus:
        return _permitted_unless(
            self.mode not in _READ_MODES, FileLogicStatus.READ_NOT_PERMITTED
        )

    def write_check(self) -> FileLogicStatus:
        return _permitted_unless(
            self.mode not in self._write_modes(), FileLogicStatus.WRITE_NOT_PERMITTED
        )

    def update_check(self) -> FileLogicStatus:
        if self.mode is not OpenMode.IO:
            return FileLogicStatus.UPDATE_NOT_PERMITTED
        return _permitted_unless(
            self._sequential() and self.position is not FilePosition.CURRENT_RECORD,
            FileLogicStatus.NO_CURRENT_RECORD,
        )

    def delete_check(self, key: str) -> FileLogicStatus:
        if self.mode is not OpenMode.IO:
            return FileLogicStatus.UPDATE_NOT_PERMITTED
        return _permitted_unless(
            not key and self.position is not FilePosition.CURRENT_RECORD,
            FileLogicStatus.NO_CURRENT_RECORD,
        )

    def key_bytes(self, key: str) -> bytes:
        if not key:
            return b""
        if self.organization is FileOrganization.RELATIVE:
            return int(key).to_bytes(_RELATIVE_KEY_BYTES, "big")
        return key.encode("latin-1")

    def after_read(self, condition: AccessCondition) -> OpenFile:
        return replace(
            self,
            position=_READ_POSITIONS.get(condition, FilePosition.NO_CURRENT_RECORD),
        )

    def after_other(self, condition: AccessCondition) -> OpenFile:
        return replace(self, position=FilePosition.NO_CURRENT_RECORD)
