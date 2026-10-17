# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from itertools import count, takewhile
from pathlib import Path
from types import MappingProxyType

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.absent_file_driver import AbsentFileDriver
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.described_slot import DescribedSlot
from interpreter.cobol.file_attributes import FileAttributes
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    RelativeDriver,
    open_driver,
)
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_verb import FileVerb
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
from interpreter.cobol.open_file import OpenFile
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.sort_field import sort_fields
from interpreter.cobol.sort_order import ordered
from interpreter.cobol.variable_sequential_driver import VariableSequentialDriver
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
            return IOResult(_file_status(result.condition), None, result.record_number)
        case raw:
            return IOResult(
                _file_status(result.condition),
                raw.decode("latin-1"),
                result.record_number,
            )


logger = logging.getLogger(__name__)
_UNCOMPUTABLE = Operators.UNCOMPUTABLE
_PATH_MARKS = frozenset("/\\.")
_OPEN_FAILED = to_ioresult(AccessResult(AccessCondition.FILE_NOT_FOUND))
_SUCCESSFUL_STATUS = _file_status(AccessCondition.OK)
_OPTIONAL_ABSENT = IOResult("05", None)
_VARIABLE_DRIVERS: dict[FileOrganization, Callable[[], FileOrganizationDriver]] = {
    FileOrganization.SEQUENTIAL: VariableSequentialDriver,
    FileOrganization.RELATIVE: lambda: RelativeDriver(DescribedSlot()),
}
_COPIED = to_ioresult(AccessResult(AccessCondition.OK))


def _locked_by(filename: str, closed: IOResult) -> frozenset[str]:
    return frozenset({filename}) if closed.status == _SUCCESSFUL_STATUS else frozenset()


def _successful(result: IOResult) -> bool:
    return result.status.startswith("0")


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

    def _driver_for(
        self,
        filename: str,
        attributes: FileAttributes,
        path: Path,
        mode: OpenMode,
        record_length: int,
    ) -> FileOrganizationDriver:
        if attributes.variable and attributes.organization in _VARIABLE_DRIVERS:
            drv = _VARIABLE_DRIVERS[attributes.organization]()
            drv.open(path, mode, record_length, 0, 0)
            return drv
        return self._driver(
            filename,
            attributes.organization,
            path,
            mode,
            record_length,
            attributes.prime_key.offset,
            attributes.prime_key.length,
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
        access_mode: str,
        relative_key_digits: int,
        optional: bool,
        variable: bool,
        program: str,
    ) -> IOResult:
        attributes = FileAttributes(
            _organization_of(organization),
            AccessMode(access_mode),
            PrimeKey(key_offset, key_length),
            relative_key_digits,
            optional,
            variable,
        )
        refusals = self._open_refusals(filename, OpenMode(mode), optional)
        if refusals:
            logger.warning("OPEN %s %s refused: %s", mode, filename, refusals[0].status)
            return refusals[0]
        if self._optional_absent(filename, OpenMode(mode), optional):
            return self._open_absent(
                filename, OpenMode(mode), attributes, record_length
            )
        return self._open_closed(filename, OpenMode(mode), attributes, record_length)

    def _open_refusals(
        self, filename: str, mode: OpenMode, optional: bool
    ) -> list[IOResult]:
        checks = (
            (filename in self._files, FileLogicStatus.ALREADY_OPEN.result()),
            (filename in self._locked, FileLogicStatus.CLOSED_WITH_LOCK.result()),
            (
                mode is OpenMode.EXTEND
                and not optional
                and not self._path(filename).exists(),
                _OPEN_FAILED,
            ),
        )
        return [result for refused, result in checks if refused]

    def _path(self, filename: str) -> Path:
        return self._resolve_path(filename, self._assign_to(filename))

    def _optional_absent(self, filename: str, mode: OpenMode, optional: bool) -> bool:
        absent = not self._path(filename).exists()
        return optional and absent and mode is not OpenMode.OUTPUT

    def _open_absent(
        self,
        filename: str,
        mode: OpenMode,
        attributes: FileAttributes,
        record_length: int,
    ) -> IOResult:
        logger.info("OPEN %s %s: optional file absent", mode.value, filename)
        if mode is OpenMode.INPUT:
            self._files = {
                **self._files,
                filename: OpenFile(AbsentFileDriver(), mode, attributes),
            }
            return _OPTIONAL_ABSENT
        self._path(filename).touch()
        opened = self._open_closed(filename, mode, attributes, record_length)
        return _OPTIONAL_ABSENT if opened.status == _SUCCESSFUL_STATUS else opened

    def _open_closed(
        self,
        filename: str,
        mode: OpenMode,
        attributes: FileAttributes,
        record_length: int,
    ) -> IOResult:
        path = self._path(filename)
        try:
            drv = self._driver_for(filename, attributes, path, mode, record_length)
        except OSError as exc:
            logger.warning("OPEN %s at %s failed: %s", filename, path, exc)
            return _OPEN_FAILED
        return self._opened(filename, OpenFile(drv, mode, attributes), path)

    def _opened(self, filename: str, file: OpenFile, path: Path) -> IOResult:
        self._files = {**self._files, filename: file}
        logger.info(
            "OPEN %s mode=%s org=%s access=%s path=%s",
            filename,
            file.mode.value,
            file.attributes.organization.value,
            file.attributes.access.value,
            path,
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
            self._files = {**self._files, filename: file.after_refusal()}
            return check.result()
        return self._performed(filename, file, verb)

    def _performed(self, filename: str, file: OpenFile, verb: FileVerb) -> IOResult:
        result = verb.action(file)
        self._files = {**self._files, filename: verb.after(file, result)}
        outcome = verb.outcome(file, result)
        if outcome is not FileLogicStatus.PERMITTED:
            return outcome.result()
        return to_ioresult(result)

    def _read_record(self, filename: str, key: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.READ_NOT_PERMITTED,
            FileVerb(
                lambda file: file.read_check(not key),
                lambda file: (
                    file.driver.read_key(file.key_bytes(key))
                    if key
                    else file.driver.read_seq()
                ),
                OpenFile.after_read,
                OpenFile.read_outcome,
            ),
        )

    def _write_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        record = data.encode("latin-1")
        return self._verb(
            filename,
            FileLogicStatus.WRITE_NOT_PERMITTED,
            FileVerb(
                lambda file: file.write_check(record, key),
                lambda file: file.driver.write(record, file.key_bytes(key)),
                lambda file, result: file.after_write(record, result),
            ),
        )

    def _rewrite_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        record = data.encode("latin-1")
        return self._verb(
            filename,
            FileLogicStatus.UPDATE_NOT_PERMITTED,
            FileVerb(
                lambda file: file.rewrite_check(record),
                lambda file: file.driver.rewrite(record, file.key_bytes(key)),
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
                lambda file: file.driver.start(file.key_bytes(key), relop or ">="),
                OpenFile.after_other,
            ),
        )

    def _delete_record(self, filename: str, key: str, program: str) -> IOResult:
        return self._verb(
            filename,
            FileLogicStatus.UPDATE_NOT_PERMITTED,
            FileVerb(
                OpenFile.delete_check,
                lambda file: file.driver.delete(file.key_bytes(key)),
                OpenFile.after_other,
            ),
        )

    def _records(self, filename: str, program: str) -> Iterator[str]:
        reads = (self._read_record(filename, "", program) for _ in count())
        return (read.data or "" for read in takewhile(_successful, reads))

    def _copied(self, source: str, target: str, program: str) -> IOResult:
        written = [
            self._write_record(target, data, "", program)
            for data in self._records(source, program)
        ]
        return next((w for w in written if not _successful(w)), _COPIED)

    def _sort_using(self, sort_file: str, filename: str, program: str) -> IOResult:
        return self._copied(filename, sort_file, program)

    def _sort_giving(self, sort_file: str, filename: str, program: str) -> IOResult:
        return self._copied(sort_file, filename, program)

    def _reopened(
        self, sort_file: str, mode: OpenMode, record_length: int, program: str
    ) -> IOResult:
        self._close_file(sort_file, program)
        return self._open_file(
            sort_file,
            mode.value,
            record_length,
            FileOrganization.SEQUENTIAL.value,
            0,
            0,
            AccessMode.SEQUENTIAL.value,
            0,
            False,
            False,
            program,
        )

    def _sort_file(
        self,
        sort_file: str,
        record_length: int,
        weights: str,
        *keys_then_program: int | str,
    ) -> IOResult:
        program = str(keys_then_program[-1])
        self._reopened(sort_file, OpenMode.INPUT, record_length, program)
        records = [r.encode("latin-1") for r in self._records(sort_file, program)]
        self._reopened(sort_file, OpenMode.OUTPUT, record_length, program)
        _ = [
            self._write_record(sort_file, record.decode("latin-1"), "", program)
            for record in ordered(
                records,
                sort_fields(keys_then_program[:-1]),
                tuple(ord(w) for w in weights),
            )
        ]
        return self._close_file(sort_file, program)
