# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import FileOrganization, OpenMode
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    open_driver,
)
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_verb import FileVerb
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
from interpreter.cobol.open_file import OpenFile
from interpreter.vm.vm import Operators

_FILE_STATUS: dict[AccessCondition, str] = {
    AccessCondition.OK: "00",
    AccessCondition.DUPLICATES_FOLLOW: "02",
    AccessCondition.END_OF_FILE: "10",
    AccessCondition.DUPLICATE_KEY: "22",
    AccessCondition.NOT_FOUND: "23",
    AccessCondition.FILE_NOT_FOUND: "35",
    AccessCondition.ATTRIBUTE_CONFLICT: "39",
    AccessCondition.BOUNDARY_VIOLATION: "44",
    AccessCondition.OPEN_MODE_NOT_SUPPORTED: "37",
    AccessCondition.NOT_OPEN: "47",
    AccessCondition.WRITE_NOT_PERMITTED: "48",
}


def _file_status(condition: AccessCondition) -> str:
    return _FILE_STATUS[condition]


def to_ioresult(result: AccessResult) -> IOResult:
    match result.data:
        case None:
            return IOResult(_file_status(result.condition), None)
        case raw:
            return IOResult(_file_status(result.condition), raw.decode("latin-1"))


logger = logging.getLogger(__name__)
_UNCOMPUTABLE = Operators.UNCOMPUTABLE
_PATH_MARKS = frozenset("/\\.")
_OPEN_FAILED = to_ioresult(AccessResult(AccessCondition.FILE_NOT_FOUND))
_CLOSED_STATUS = _file_status(AccessCondition.OK)


def _locked_by(filename: str, closed: IOResult) -> frozenset[str]:
    return frozenset({filename}) if closed.status == _CLOSED_STATUS else frozenset()


def _organization_of(organization: str) -> FileOrganization:
    try:
        return FileOrganization(organization)
    except ValueError:
        return FileOrganization.SEQUENTIAL


class RealFileIOProvider(CobolIOProvider):
    """Disk-backed COBOL I/O provider.

    Args:
        base_dir: Root for resolving relative paths from ``assign_to``.
        file_control: FileControlEntry list from the ASG.
        path_overrides: Test hook — takes precedence over all other resolution.
        system_input: The system input device's fixed-length records, which
            ACCEPT reads in order.
        switches: The run's implementor switch settings by environment name;
            a switch not named is OFF.
    """

    def __init__(
        self,
        base_dir: Path,
        file_control: Sequence[FileControlEntry] = (),
        path_overrides: Mapping[str, Path] = MappingProxyType({}),
        system_input: Sequence[str] = (),
        switches: Mapping[str, SwitchStatus] = MappingProxyType({}),
    ) -> None:
        self._base_dir = base_dir
        self._system_input: Iterator[str] = iter(system_input)
        self._switches: dict[str, SwitchStatus] = {
            name.upper(): status for name, status in switches.items()
        }
        self._fce: dict[str, FileControlEntry] = {e.file_name: e for e in file_control}
        self._overrides: Mapping[str, Path] = path_overrides
        self._files: dict[str, OpenFile] = {}
        self._locked: frozenset[str] = frozenset()

    def _overridden(self, file_name: str, assign_to: str) -> list[Path]:
        names = [file_name, *([assign_to] if assign_to else [])]
        return [self._overrides[k] for k in names if k in self._overrides]

    def _from_environment(self, clean: str) -> Path:
        bare = not set(clean) & _PATH_MARKS
        env_val = os.environ.get(clean.upper(), "") if bare else ""
        return Path(env_val) if env_val else self._base_dir / clean

    def _assigned(self, file_name: str, assign_to: str) -> Path:
        if not assign_to:
            return self._base_dir / (file_name.lower().replace("-", "_") + ".dat")
        return self._from_environment(assign_to.strip("'\""))

    def _resolve_path(self, file_name: str, assign_to: str) -> Path:
        return next(
            iter(self._overridden(file_name, assign_to)),
            self._assigned(file_name, assign_to),
        )

    def _switch_status(self, environment_name: str) -> str:
        return self._switches.get(environment_name.upper(), SwitchStatus.OFF).value

    def _set_switch(self, environment_name: str, status: str) -> IOResult:
        self._switches = {
            **self._switches,
            environment_name.upper(): SwitchStatus(status),
        }
        return IOResult("00", None)

    def _accept(self, from_device: str) -> str | Operators._Uncomputable:
        return next(self._system_input, _UNCOMPUTABLE)

    def _accept_area(
        self, from_device: str, length: int
    ) -> str | Operators._Uncomputable:
        match self._accept(from_device):
            case str() as record:
                return self._filled(record, from_device, length)
            case end:
                return end

    def _filled(self, received: str, from_device: str, length: int) -> str:
        if len(received) >= length:
            return received[:length]
        match self._accept(from_device):
            case str() as record:
                return self._filled(received + record, from_device, length)
            case _:
                return received

    def _driver(
        self,
        filename: str,
        org: FileOrganization,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> FileOrganizationDriver:
        return open_driver(
            org,
            path,
            mode,
            record_length,
            key_offset,
            key_length,
        )

    def _assign_to(self, filename: str) -> str:
        return self._fce[filename].assign_to if filename in self._fce else ""

    def _open_file(
        self,
        filename: str,
        mode: str,
        record_length: int,
        organization: str,
        key_offset: int,
        key_length: int,
        program: str,
    ) -> IOResult:
        refusals = self._open_refusals(filename, OpenMode(mode))
        if refusals:
            logger.warning("OPEN %s %s refused: %s", mode, filename, refusals[0].status)
            return refusals[0]
        return self._open_closed(
            filename,
            OpenMode(mode),
            record_length,
            organization,
            key_offset,
            key_length,
        )

    def _open_refusals(self, filename: str, mode: OpenMode) -> list[IOResult]:
        checks = (
            (filename in self._files, FileLogicStatus.ALREADY_OPEN.result()),
            (filename in self._locked, FileLogicStatus.CLOSED_WITH_LOCK.result()),
            (self._extending_absent(filename, mode), _OPEN_FAILED),
        )
        return [result for refused, result in checks if refused]

    def _extending_absent(self, filename: str, mode: OpenMode) -> bool:
        path = self._resolve_path(filename, self._assign_to(filename))
        return mode is OpenMode.EXTEND and not path.exists()

    def _open_closed(
        self,
        filename: str,
        mode: OpenMode,
        record_length: int,
        organization: str,
        key_offset: int,
        key_length: int,
    ) -> IOResult:
        org = _organization_of(organization)
        path = self._resolve_path(filename, self._assign_to(filename))
        try:
            drv = self._driver(
                filename,
                org,
                path,
                mode,
                record_length,
                key_offset,
                key_length,
            )
        except FileNotFoundError:
            logger.warning("OPEN %s: file not found at %s", filename, path)
            return _OPEN_FAILED
        except OSError as exc:
            logger.warning("OPEN %s failed: %s", filename, exc)
            return _OPEN_FAILED
        return self._opened(filename, mode, org, path, drv)

    def _opened(
        self,
        filename: str,
        mode: OpenMode,
        org: FileOrganization,
        path: Path,
        drv: FileOrganizationDriver,
    ) -> IOResult:
        self._files = {**self._files, filename: OpenFile(drv, mode, org)}
        logger.info(
            "OPEN %s mode=%s org=%s path=%s", filename, mode.value, org.value, path
        )
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _close_file(self, filename: str, program: str) -> IOResult:
        if filename not in self._files:
            return FileLogicStatus.NOT_OPEN.result()
        self._files[filename].driver.close()
        self._files = {k: f for k, f in self._files.items() if k != filename}
        logger.info("CLOSE %s", filename)
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _close_file_with_lock(self, filename: str, program: str) -> IOResult:
        closed = self._close_file(filename, program)
        self._locked = self._locked | _locked_by(filename, closed)
        return closed

    def _open_mode(self, filename: str, program: str) -> str:
        return self._files[filename].mode.value if filename in self._files else ""

    def _verb(
        self,
        filename: str,
        refused_when_closed: FileLogicStatus,
        verb: FileVerb,
    ) -> IOResult:
        if filename not in self._files:
            return refused_when_closed.result()
        file = self._files[filename]
        check = verb.check(file)
        if check is not FileLogicStatus.PERMITTED:
            return check.result()
        result = verb.action(file.driver)
        self._files = {**self._files, filename: verb.after(file, result.condition)}
        return to_ioresult(result)

    def _read_record(self, filename: str, key: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.READ_NOT_PERMITTED,
            FileVerb(
                lambda file: file.read_check(not key),
                lambda drv: (
                    drv.read_key(key.encode("latin-1")) if key else drv.read_seq()
                ),
                OpenFile.after_read,
            ),
        )

    def _write_record(self, filename: str, data: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.WRITE_NOT_PERMITTED,
            FileVerb(
                OpenFile.write_check,
                lambda drv: drv.write(data.encode("latin-1")),
                OpenFile.after_other,
            ),
        )

    def _rewrite_record(self, filename: str, data: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.UPDATE_NOT_PERMITTED,
            FileVerb(
                OpenFile.update_check,
                lambda drv: drv.rewrite(data.encode("latin-1")),
                OpenFile.after_other,
            ),
        )

    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.READ_NOT_PERMITTED,
            FileVerb(
                OpenFile.start_check,
                lambda drv: drv.start(
                    key.encode("latin-1") if key else b"", relop or ">="
                ),
                OpenFile.after_other,
            ),
        )

    def _delete_record(self, filename: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.UPDATE_NOT_PERMITTED,
            FileVerb(
                OpenFile.update_check, lambda drv: drv.delete(), OpenFile.after_other
            ),
        )
