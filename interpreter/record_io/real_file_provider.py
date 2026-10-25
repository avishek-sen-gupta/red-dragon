# pyright: standard
"""RealFileProvider — disk-backed record I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.data_value import DataRecord
from interpreter.record_io.access_result import AccessCondition, AccessResult
from interpreter.record_io.described_slot import DescribedSlot
from interpreter.record_io.file_drivers import (
    FileOrganizationDriver,
    RelativeDriver,
    open_driver,
)
from interpreter.record_io.file_frame import FileFrame, frame_of
from interpreter.record_io.io_provider import IOResult, RecordIOProvider
from interpreter.record_io.prime_key import PrimeKey
from interpreter.record_io.run_inputs import NO_RUN_INPUTS, RunInputs
from interpreter.record_io.variable_sequential_driver import VariableSequentialDriver


def to_ioresult(result: AccessResult) -> IOResult:
    match result.data:
        case None:
            return IOResult(result.condition, None, result.record_number)
        case raw:
            return IOResult(
                result.condition,
                raw.decode("latin-1"),
                result.record_number,
            )


logger = logging.getLogger(__name__)
_RELATIVE_NUMBER_BYTES = 4
_OPEN_FAILED = to_ioresult(AccessResult(AccessCondition.FILE_NOT_FOUND))
_VARIABLE_DRIVERS: dict[FileOrganization, Callable[[], FileOrganizationDriver]] = {
    FileOrganization.SEQUENTIAL: VariableSequentialDriver,
    FileOrganization.RELATIVE: lambda: RelativeDriver(DescribedSlot()),
}


class RealFileProvider(RecordIOProvider):
    """Disk-backed record I/O provider. It opens a file only at the path the run's
    inputs give its name; a name with no path fails the open.

    Args:
        inputs: The run's path overrides, one path per file name.
    """

    def __init__(self, inputs: RunInputs = NO_RUN_INPUTS) -> None:
        self._overrides: Mapping[str, Path] = inputs.path_overrides
        self._files: dict[str, FileOrganizationDriver] = {}
        self._frames: dict[str, FileFrame] = {}

    def _paths(self, filename: str) -> tuple[Path, ...]:
        return tuple(self._overrides[k] for k in (filename,) if k in self._overrides)

    def _driver(
        self, frame: FileFrame, path: Path, mode: OpenMode
    ) -> FileOrganizationDriver:
        return open_driver(path, mode, frame.shape())

    def _driver_for(
        self, frame: FileFrame, path: Path, mode: OpenMode
    ) -> FileOrganizationDriver:
        if frame.variable and frame.organization in _VARIABLE_DRIVERS:
            drv = _VARIABLE_DRIVERS[frame.organization]()
            drv.open(path, mode, frame.record_length, PrimeKey())
            return drv
        return self._driver(frame, path, mode)

    def _declare_file(self, frame: DataRecord, program: str) -> IOResult:
        declared = frame_of(frame)
        self._frames = {**self._frames, declared.file_name: declared}
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        paths = self._paths(filename)
        if not paths:
            logger.info("OPEN %s %s: no path", mode, filename)
            return _OPEN_FAILED
        return self._open_at(filename, OpenMode(mode), paths[0])

    def _open_at(self, filename: str, mode: OpenMode, path: Path) -> IOResult:
        if mode is not OpenMode.OUTPUT and not path.exists():
            logger.info("OPEN %s %s: no such file", mode.value, filename)
            return _OPEN_FAILED
        return self._open_closed(filename, mode, self._frames[filename], path)

    def _open_closed(
        self, filename: str, mode: OpenMode, frame: FileFrame, path: Path
    ) -> IOResult:
        try:
            drv = self._driver_for(frame, path, mode)
        except OSError as exc:
            logger.warning("OPEN %s at %s failed: %s", filename, path, exc)
            return _OPEN_FAILED
        self._files = {**self._files, filename: drv}
        logger.info(
            "OPEN %s mode=%s org=%s path=%s",
            filename,
            mode.value,
            frame.organization.value,
            path,
        )
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _close_file(self, filename: str, program: str) -> IOResult:
        if filename not in self._files:
            return to_ioresult(AccessResult(AccessCondition.NOT_OPEN))
        self._files[filename].close()
        self._files = {k: f for k, f in self._files.items() if k != filename}
        logger.info("CLOSE %s", filename)
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _locator_bytes(self, filename: str, locator: str) -> bytes:
        if not locator:
            return b""
        if self._frames[filename].organization is FileOrganization.RELATIVE:
            return int(locator).to_bytes(_RELATIVE_NUMBER_BYTES, "big")
        return locator.encode("latin-1")

    def _read_record(self, filename: str, locator: str, program: str) -> IOResult:
        driver = self._files[filename]
        if locator:
            located = self._locator_bytes(filename, locator)
            return to_ioresult(driver.read_key(located))
        return to_ioresult(driver.read_seq())

    def _write_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].write(
                data.encode("latin-1"), self._locator_bytes(filename, locator)
            )
        )

    def _rewrite_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].rewrite(
                data.encode("latin-1"), self._locator_bytes(filename, locator)
            )
        )

    def _start_file(
        self, filename: str, locator: str, relop: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].start(
                self._locator_bytes(filename, locator), relop or ">="
            )
        )

    def _delete_record(self, filename: str, locator: str, program: str) -> IOResult:
        return to_ioresult(
            self._files[filename].delete(self._locator_bytes(filename, locator))
        )
