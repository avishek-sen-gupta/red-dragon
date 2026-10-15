# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    open_driver,
)
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
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
_NOT_OPEN = to_ioresult(AccessResult(AccessCondition.NOT_OPEN))
_OPEN_FAILED = to_ioresult(AccessResult(AccessCondition.FILE_NOT_FOUND))


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
    """

    def __init__(
        self,
        base_dir: Path,
        file_control: Sequence[FileControlEntry] = (),
        path_overrides: Mapping[str, Path] = MappingProxyType({}),
    ) -> None:
        self._base_dir = base_dir
        self._fce: dict[str, FileControlEntry] = {e.file_name: e for e in file_control}
        self._overrides: Mapping[str, Path] = path_overrides
        self._drivers: dict[str, FileOrganizationDriver] = {}
        self._open_modes: dict[str, str] = {}

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

    def _accept(self, from_device: str) -> Operators._Uncomputable:
        return _UNCOMPUTABLE

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
        org = _organization_of(organization)
        path = self._resolve_path(filename, self._assign_to(filename))
        try:
            drv = self._driver(
                filename,
                org,
                path,
                OpenMode(mode),
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
        mode: str,
        org: FileOrganization,
        path: Path,
        drv: FileOrganizationDriver,
    ) -> IOResult:
        self._drivers = {**self._drivers, filename: drv}
        self._open_modes = {**self._open_modes, filename.upper(): mode}
        logger.info("OPEN %s mode=%s org=%s path=%s", filename, mode, org.value, path)
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _close_file(self, filename: str, program: str) -> IOResult:
        drv = self._drivers.pop(filename, None)
        if drv:
            drv.close()
        self._open_modes.pop(filename.upper(), None)
        logger.info("CLOSE %s", filename)
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _open_mode(self, filename: str, program: str) -> str:
        return self._open_modes.get(str(filename).upper(), "")

    def _with_driver(
        self,
        filename: str,
        action: Callable[[FileOrganizationDriver], AccessResult],
    ) -> IOResult:
        if filename not in self._drivers:
            return _NOT_OPEN
        return to_ioresult(action(self._drivers[filename]))

    def _read_record(self, filename: str, key: str, program: str) -> IOResult:
        return self._with_driver(
            filename,
            lambda drv: drv.read_key(key.encode("latin-1")) if key else drv.read_seq(),
        )

    def _write_record(self, filename: str, data: str, program: str) -> IOResult:
        return self._with_driver(
            filename, lambda drv: drv.write(data.encode("latin-1"))
        )

    def _rewrite_record(self, filename: str, data: str, program: str) -> IOResult:
        return self._with_driver(
            filename, lambda drv: drv.rewrite(data.encode("latin-1"))
        )

    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        return self._with_driver(
            filename,
            lambda drv: drv.start(key.encode("latin-1") if key else b"", relop or ">="),
        )

    def _delete_record(self, filename: str, program: str) -> IOResult:
        return self._with_driver(filename, lambda drv: drv.delete())
