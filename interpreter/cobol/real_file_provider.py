# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from interpreter.cobol.cobol_statements import FileControlEntry
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
)
from interpreter.cobol.file_enums import FileOrganization, OpenMode
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)
_UNCOMPUTABLE = Operators.UNCOMPUTABLE


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
        file_control: list[FileControlEntry] | None = None,
        path_overrides: dict[str, Path] | None = None,
    ) -> None:
        self._base_dir = base_dir
        self._fce: dict[str, FileControlEntry] = {
            e.file_name: e for e in (file_control or [])
        }
        self._overrides: dict[str, Path] = path_overrides or {}
        self._drivers: dict[str, FileOrganizationDriver] = {}

    def _resolve_path(self, file_name: str, assign_to: str) -> Path:
        if file_name in self._overrides:
            return self._overrides[file_name]
        if assign_to:
            clean = assign_to.strip("'\"")
            # If it looks like a bare identifier (no path separators, no extension),
            # check environment variable first.
            if "/" not in clean and "\\" not in clean and "." not in clean:
                env_val = os.environ.get(clean.upper())
                if env_val:
                    return Path(env_val)
            return self._base_dir / clean
        return self._base_dir / (file_name.lower().replace("-", "_") + ".dat")

    def _accept(self, from_device: str) -> Any:
        return _UNCOMPUTABLE

    def _open_file(
        self,
        filename: str,
        mode: str,
        record_length: int,
        organization: str,
        key_offset: int,
        key_length: int,
    ) -> IOResult:
        fce = self._fce.get(filename)
        assign_to = fce.assign_to if fce else ""
        # Use organization from call args (comes from lower_io metadata)
        try:
            org = FileOrganization(organization)
        except ValueError:
            org = FileOrganization.SEQUENTIAL

        path = self._resolve_path(filename, assign_to)
        open_mode = OpenMode(mode)

        if org == FileOrganization.INDEXED:
            drv: FileOrganizationDriver = IndexedDriver()
        elif org == FileOrganization.RELATIVE:
            drv = RelativeDriver()
        else:
            drv = SequentialDriver()

        try:
            drv.open(path, open_mode, record_length, key_offset, key_length)
        except FileNotFoundError:
            logger.warning("OPEN %s: file not found at %s", filename, path)
            return IOResult("35", None)
        except OSError as exc:
            logger.warning("OPEN %s failed: %s", filename, exc)
            return IOResult("35", None)

        self._drivers[filename] = drv
        logger.info("OPEN %s mode=%s org=%s path=%s", filename, mode, org.value, path)
        return IOResult("00", None)

    def _close_file(self, filename: str) -> IOResult:
        drv = self._drivers.pop(filename, None)
        if drv:
            drv.close()
        logger.info("CLOSE %s", filename)
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str) -> IOResult:
        drv = self._drivers.get(filename)
        if drv is None:
            return IOResult("47", None)
        if key:
            return drv.read_key(key.encode("latin-1"))
        return drv.read_seq()

    def _write_record(self, filename: str, data: str) -> IOResult:
        drv = self._drivers.get(filename)
        if drv is None:
            return IOResult("47", None)
        return drv.write(data.encode("latin-1"))

    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        drv = self._drivers.get(filename)
        if drv is None:
            return IOResult("47", None)
        return drv.rewrite(data.encode("latin-1"))

    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        drv = self._drivers.get(filename)
        if drv is None:
            return IOResult("47", None)
        key_bytes = key.encode("latin-1") if key else b""
        return drv.start(key_bytes, relop or ">=")

    def _delete_record(self, filename: str) -> IOResult:
        drv = self._drivers.get(filename)
        if drv is None:
            return IOResult("47", None)
        return drv.delete()
