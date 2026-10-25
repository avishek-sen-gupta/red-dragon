# pyright: standard
"""The COBOL file provider: the record operations plus what only COBOL asks of a provider
(ACCEPT FROM a device and the implementor switches and KEY OF REFERENCE).

Two implementations:
- NullIOProvider: returns UNCOMPUTABLE for READ; IOResult(AccessCondition.OK, None) for all other ops.
- StubIOProvider: returns queued test data for concrete execution without files.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from cobol_asg.switch_status import SwitchStatus
from infrastructure.zos.access_methods.access_result import AccessCondition
from interpreter.func_name import FuncName
from interpreter.record_io.io_provider import (
    RECORD_OPERATIONS,
    IOResult,
    RecordIOProvider,
)
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)

_UNCOMPUTABLE = Operators.UNCOMPUTABLE

# Dispatch table mapping __cobol_* function names to provider method names.
_COBOL_IO_DISPATCH: dict[FuncName, str] = {
    **RECORD_OPERATIONS,
    FuncName("__cobol_accept"): "_accept",
    FuncName("__cobol_key_of_reference"): "_key_of_reference",
    FuncName("__cobol_switch_status"): "_switch_status",
    FuncName("__cobol_set_switch"): "_set_switch",
}


class CobolIOProvider(RecordIOProvider):
    """A record provider that also serves COBOL's ACCEPT, implementor switches and
    KEY OF REFERENCE."""

    operations = _COBOL_IO_DISPATCH

    def _switch_status(self, environment_name: str) -> str:
        """An implementor switch's status, "ON" or "OFF": OFF unless supplied, as
        IBM's UPSI run-time option defaults every switch off."""
        return SwitchStatus.OFF.value

    def _set_switch(self, environment_name: str, status: str) -> IOResult:
        """SET mnemonic-name TO ON|OFF. A provider that keeps no switch state
        ignores it."""
        return IOResult(AccessCondition.OK, None)

    @abstractmethod
    def _accept(self, from_device: str) -> IOResult | Operators._Uncomputable:
        """ACCEPT: the device's next input record, END_OF_FILE when its input has
        ended, UNCOMPUTABLE when the input is unknown. The lowering fills the
        receiving area from successive records."""
        ...

    @abstractmethod
    def _key_of_reference(
        self, filename: str, number: int, program: str
    ) -> IOResult: ...


@dataclass
class StubFile:
    """In-memory file stub for testing — holds read records and captures writes."""

    records: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    is_open: bool = False


class NullIOProvider(CobolIOProvider):
    """Default provider — returns UNCOMPUTABLE for READ, IOResult(AccessCondition.OK, None) for all other ops."""

    def _accept(self, from_device: str) -> Operators._Uncomputable:
        return _UNCOMPUTABLE

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _close_file(self, filename: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _read_record(self, filename: str, locator: str, program: str) -> Any:
        return _UNCOMPUTABLE

    def _write_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _rewrite_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _start_file(
        self, filename: str, locator: str, relop: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _delete_record(self, filename: str, locator: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _key_of_reference(self, filename: str, number: int, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)


class StubIOProvider(CobolIOProvider):
    """Test provider — returns queued data for ACCEPT/READ, captures WRITE output.

    Usage:
        stubs = StubIOProvider(
            accept_values=["Y", "JOHN DOE"],
            files={"CUSTOMER-FILE": {"records": ["REC1DATA", "REC2DATA"]}},
        )
        vm = run(source, language="cobol", io_provider=stubs)

        # Inspect written records:
        stubs.get_file("OUTPUT-FILE").written  # → ["RESULT1", "RESULT2"]
    """

    def __init__(
        self,
        accept_values: list[str] = [],
        files: dict[str, dict[str, Any]] = {},
    ):
        self._accept_queue: Iterator[str] = iter(list(accept_values))
        self._files: dict[str, StubFile] = {
            name: StubFile(records=list(f.get("records", [])))
            for name, f in files.items()
        }

    def get_file(self, filename: str) -> StubFile:
        """Get the StubFile for a filename, creating one if absent."""
        if filename not in self._files:
            self._files = {**self._files, filename: StubFile()}
        return self._files[filename]

    def _accept(self, from_device: str) -> IOResult | Operators._Uncomputable:
        return next(
            (IOResult(AccessCondition.OK, value) for value in self._accept_queue),
            _UNCOMPUTABLE,
        )

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        stub = self.get_file(filename)
        stub.is_open = True
        logger.info("StubIOProvider OPEN %s mode=%s", filename, mode)
        return IOResult(AccessCondition.OK, None)

    def _close_file(self, filename: str, program: str) -> IOResult:
        if filename in self._files:
            self._files[filename].is_open = False
        logger.info("StubIOProvider CLOSE %s", filename)
        return IOResult(AccessCondition.OK, None)

    def _read_record(self, filename: str, locator: str, program: str) -> Any:
        stub = self._files.get(filename)
        if stub and stub.records:
            record = stub.records.pop(0)
            logger.info("StubIOProvider READ %s → %r", filename, record)
            return IOResult(AccessCondition.OK, record)
        logger.info("StubIOProvider READ %s → AT END", filename)
        return IOResult(AccessCondition.END_OF_FILE, None)

    def _write_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        stub = self.get_file(filename)
        stub.written.append(data)
        logger.info("StubIOProvider WRITE %s ← %r", filename, data)
        return IOResult(AccessCondition.OK, None)

    def _rewrite_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        stub = self.get_file(filename)
        if stub.written:
            stub.written[-1] = data
        else:
            stub.written.append(data)
        logger.info("StubIOProvider REWRITE %s ← %r", filename, data)
        return IOResult(AccessCondition.OK, None)

    def _start_file(
        self, filename: str, locator: str, relop: str, program: str
    ) -> IOResult:
        logger.info(
            "StubIOProvider START %s locator=%s relop=%s (no-op)",
            filename,
            locator,
            relop,
        )
        return IOResult(AccessCondition.OK, None)

    def _delete_record(self, filename: str, locator: str, program: str) -> IOResult:
        stub = self._files.get(filename)
        if stub and stub.records:
            removed = stub.records.pop(0)
            logger.info("StubIOProvider DELETE %s → removed %r", filename, removed)
        else:
            logger.info("StubIOProvider DELETE %s → no records", filename)
        return IOResult(AccessCondition.OK, None)

    def _key_of_reference(self, filename: str, number: int, program: str) -> IOResult:
        logger.info("StubIOProvider KEY OF REFERENCE %s = %d (no-op)", filename, number)
        return IOResult(AccessCondition.OK, None)
