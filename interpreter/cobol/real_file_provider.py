# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator, Mapping
from itertools import count, takewhile
from pathlib import Path

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import FileOrganization, OpenMode
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.described_slot import DescribedSlot
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    RelativeDriver,
    open_driver,
)
from interpreter.cobol.file_frame import FileFrame, frame_of
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.run_inputs import NO_RUN_INPUTS, RunInputs
from interpreter.cobol.sort_field import sort_fields
from interpreter.cobol.sort_order import ordered
from interpreter.cobol.variable_sequential_driver import VariableSequentialDriver
from interpreter.data_value import DataRecord


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
_INPUT_ENDED = IOResult(AccessCondition.END_OF_FILE, None)
_SUCCESSFUL = frozenset({AccessCondition.OK, AccessCondition.DUPLICATES_FOLLOW})
_PATH_MARKS = frozenset("/\\.")
_RELATIVE_KEY_BYTES = 4
_OPEN_FAILED = to_ioresult(AccessResult(AccessCondition.FILE_NOT_FOUND))
_VARIABLE_DRIVERS: dict[FileOrganization, Callable[[], FileOrganizationDriver]] = {
    FileOrganization.SEQUENTIAL: VariableSequentialDriver,
    FileOrganization.RELATIVE: lambda: RelativeDriver(DescribedSlot()),
}
_COPIED = to_ioresult(AccessResult(AccessCondition.OK))


def _successful(result: IOResult) -> bool:
    return result.condition in _SUCCESSFUL


class RealFileIOProvider(CobolIOProvider):
    """Disk-backed COBOL I/O provider.

    Args:
        base_dir: Root for resolving relative paths from ``assign_to``.
        inputs: The run's SELECT entries, path overrides (which take precedence
            over all other resolution), system input records (which ACCEPT reads
            in order) and implementor switch settings (a switch not named is OFF).
    """

    def __init__(self, base_dir: Path, inputs: RunInputs = NO_RUN_INPUTS) -> None:
        self._base_dir = base_dir
        self._system_input: Iterator[str] = iter(inputs.system_input)
        self._switches: dict[str, SwitchStatus] = {
            name.upper(): status for name, status in inputs.switches.items()
        }
        self._fce: dict[str, FileControlEntry] = {
            e.file_name: e for e in inputs.file_control
        }
        self._overrides: Mapping[str, Path] = inputs.path_overrides
        self._files: dict[str, FileOrganizationDriver] = {}
        self._frames: dict[str, FileFrame] = {}

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
        return IOResult(AccessCondition.OK, None)

    def _accept(self, from_device: str) -> IOResult:
        return next(
            (IOResult(AccessCondition.OK, record) for record in self._system_input),
            _INPUT_ENDED,
        )

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

    def _assign_to(self, filename: str) -> str:
        return self._fce[filename].assign_to if filename in self._fce else ""

    def _declare_file(self, frame: DataRecord, program: str) -> IOResult:
        declared = frame_of(frame)
        self._frames = {**self._frames, declared.file_name: declared}
        return to_ioresult(AccessResult(AccessCondition.OK))

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        if self._absent(filename, OpenMode(mode)):
            logger.info("OPEN %s %s: no such file", mode, filename)
            return _OPEN_FAILED
        return self._open_closed(filename, OpenMode(mode), self._frames[filename])

    def _absent(self, filename: str, mode: OpenMode) -> bool:
        return mode is not OpenMode.OUTPUT and not self._path(filename).exists()

    def _path(self, filename: str) -> Path:
        return self._resolve_path(filename, self._assign_to(filename))

    def _open_closed(self, filename: str, mode: OpenMode, frame: FileFrame) -> IOResult:
        path = self._path(filename)
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

    def _key_bytes(self, filename: str, key: str) -> bytes:
        if not key:
            return b""
        if self._frames[filename].organization is FileOrganization.RELATIVE:
            return int(key).to_bytes(_RELATIVE_KEY_BYTES, "big")
        return key.encode("latin-1")

    def _read_record(self, filename: str, key: str, program: str) -> IOResult:
        driver = self._files[filename]
        if key:
            return to_ioresult(driver.read_key(self._key_bytes(filename, key)))
        return to_ioresult(driver.read_seq())

    def _write_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].write(
                data.encode("latin-1"), self._key_bytes(filename, key)
            )
        )

    def _rewrite_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].rewrite(
                data.encode("latin-1"), self._key_bytes(filename, key)
            )
        )

    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        return to_ioresult(
            self._files[filename].start(self._key_bytes(filename, key), relop or ">=")
        )

    def _delete_record(self, filename: str, key: str, program: str) -> IOResult:
        return to_ioresult(self._files[filename].delete(self._key_bytes(filename, key)))

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
        self._frames = {
            **self._frames,
            sort_file: FileFrame(
                sort_file, FileOrganization.SEQUENTIAL, PrimeKey(), False, record_length
            ),
        }
        return self._open_file(sort_file, mode.value, program)

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
