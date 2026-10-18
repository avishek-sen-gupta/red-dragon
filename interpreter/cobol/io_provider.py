# pyright: standard
"""Injectable I/O provider for COBOL statement execution.

Provides a pluggable strategy for COBOL I/O operations (ACCEPT, READ, WRITE,
OPEN, CLOSE) during symbolic execution. Similar to UnresolvedCallResolver,
this is injected via VMConfig and accessed by the executor for __cobol_*
CALL_FUNCTION dispatch.

Two implementations:
- NullIOProvider: returns UNCOMPUTABLE for READ; IOResult(AccessCondition.OK, None) for all other ops.
- StubIOProvider: returns queued test data for concrete execution without files.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.access_result import AccessCondition
from interpreter.data_value import DataRecord
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


@dataclass(frozen=True)
class IOResult:
    """Structured return value for all CobolIOProvider I/O methods.

    condition: the driver's outcome; the lowering's IR maps it to a FILE STATUS.
    data:      Populated on successful READ; None for write-side verbs.
    """

    condition: AccessCondition
    data: str | None
    record_number: int = 0


# Dispatch table mapping __cobol_* function names to provider method names.
_COBOL_IO_DISPATCH: dict[FuncName, str] = {
    FuncName("__cobol_accept"): "_accept_area",
    FuncName("__cobol_declare_file"): "_declare_file",
    FuncName("__cobol_open_file"): "_open_file",
    FuncName("__cobol_close_file"): "_close_file",
    FuncName("__cobol_read_record"): "_read_record",
    FuncName("__cobol_write_record"): "_write_record",
    FuncName("__cobol_rewrite_record"): "_rewrite_record",
    FuncName("__cobol_start_file"): "_start_file",
    FuncName("__cobol_delete_record"): "_delete_record",
    FuncName("__cobol_io_outcome"): "_io_outcome",
    FuncName("__cobol_io_data"): "_io_data",
    FuncName("__cobol_io_record_number"): "_io_record_number",
    FuncName("__cobol_switch_status"): "_switch_status",
    FuncName("__cobol_set_switch"): "_set_switch",
    FuncName("__cobol_sort_using"): "_sort_using",
    FuncName("__cobol_sort_giving"): "_sort_giving",
    FuncName("__cobol_sort_file"): "_sort_file",
}


class CobolIOProvider(ABC):
    """Abstract base for COBOL I/O handling during symbolic execution.

    The executor calls handle_call(func_name, args) for any __cobol_*
    CALL_FUNCTION instruction. Implementations decide whether to return
    concrete data or UNCOMPUTABLE (which the executor wraps as symbolic).
    """

    def dispatch(self, name: FuncName) -> str | None:
        return _COBOL_IO_DISPATCH.get(name)

    def handle_call(
        self, func_name: FuncName, args: list[TypedValue]
    ) -> Any:  # Any: str | int | IOResult | _Uncomputable — VM I/O boundary
        """Route a __cobol_* call to the appropriate method.

        Returns a concrete value or UNCOMPUTABLE if unhandled.
        """
        method_name = self.dispatch(func_name)
        if method_name is None:
            logger.debug("CobolIOProvider: unknown func %s", func_name)
            return _UNCOMPUTABLE
        method = getattr(self, method_name)
        return method(*[a.value for a in args])

    def _io_outcome(self, raw: Any, program: str) -> Any:
        """The driver outcome of an IOResult, as its AccessCondition's position."""
        if isinstance(raw, IOResult):
            return raw.condition.position()
        return _UNCOMPUTABLE

    def _io_data(self, raw: Any, program: str) -> Any:
        """Extract record data from an IOResult (empty string if None)."""
        if isinstance(raw, IOResult):
            return raw.data or ""
        return _UNCOMPUTABLE

    def _io_record_number(self, raw: IOResult, program: str) -> int:
        """The relative record number a relative-file verb used, 0 for others."""
        return raw.record_number

    def _switch_status(self, environment_name: str) -> str:
        """An implementor switch's status, "ON" or "OFF": OFF unless supplied, as
        IBM's UPSI run-time option defaults every switch off."""
        return SwitchStatus.OFF.value

    def _set_switch(self, environment_name: str, status: str) -> IOResult:
        """SET mnemonic-name TO ON|OFF. A provider that keeps no switch state
        ignores it."""
        return IOResult(AccessCondition.OK, None)

    def _sort_using(self, sort_file: str, filename: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _sort_giving(self, sort_file: str, filename: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _sort_file(
        self,
        sort_file: str,
        record_length: int,
        weights: str,
        *keys_then_program: int | str,
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _accept_area(
        self, from_device: str, length: int
    ) -> str | Operators._Uncomputable:
        """ACCEPT into a receiving area of ``length`` bytes: one message."""
        return self._accept(from_device)

    @abstractmethod
    def _accept(
        self, from_device: str
    ) -> Any:  # Any: str | _Uncomputable — VM I/O boundary
        """ACCEPT — read input from a device (e.g. CONSOLE)."""
        ...

    def _declare_file(self, frame: DataRecord, program: str) -> IOResult:
        """A program's declaration of one of its files, made once before any OPEN:
        the ``FileFrame`` record ``file_frame.frame_of`` reads. A provider that
        frames no records ignores it."""
        return IOResult(AccessCondition.OK, None)

    @abstractmethod
    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        """OPEN file in given mode (INPUT/OUTPUT/I-O/EXTEND), as its declaration
        frames it."""
        ...

    @abstractmethod
    def _close_file(self, filename: str, program: str) -> IOResult:
        """CLOSE file."""
        ...

    @abstractmethod
    def _read_record(
        self, filename: str, key: str, program: str
    ) -> Any:  # Any: IOResult | _Uncomputable
        """READ — get next record from file."""
        ...

    @abstractmethod
    def _write_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        """WRITE — write a record to file, at relative record number ``key`` if given."""
        ...

    @abstractmethod
    def _rewrite_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        """REWRITE — replace the record numbered ``key``, or the last-read one."""
        ...

    @abstractmethod
    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        """START — position file at key for sequential reading."""
        ...

    @abstractmethod
    def _delete_record(self, filename: str, key: str, program: str) -> IOResult:
        """DELETE — remove the record ``key`` names, or the last-read record
        when ``key`` is empty (sequential access)."""
        ...


@dataclass
class StubFile:
    """In-memory file stub for testing — holds read records and captures writes."""

    records: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    is_open: bool = False


class NullIOProvider(CobolIOProvider):
    """Default provider — returns UNCOMPUTABLE for READ, IOResult(AccessCondition.OK, None) for all other ops."""

    def _accept(self, from_device: str) -> Any:
        return _UNCOMPUTABLE

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _close_file(self, filename: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _read_record(self, filename: str, key: str, program: str) -> Any:
        return _UNCOMPUTABLE

    def _write_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _rewrite_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        return IOResult(AccessCondition.OK, None)

    def _delete_record(self, filename: str, key: str, program: str) -> IOResult:
        return IOResult(AccessCondition.OK, None)


class StubIOProvider(CobolIOProvider):
    """Test provider — returns queued data for ACCEPT/READ, captures WRITE output.

    Usage:
        stubs = StubIOProvider(
            accept_values=["Y", "JOHN DOE"],
            files={"CUSTOMER-FILE": {"records": ["REC1DATA", "REC2DATA"]}},
        )
        config = VMConfig(io_provider=stubs)
        vm = run(source, language="cobol", config=config)

        # Inspect written records:
        stubs.get_file("OUTPUT-FILE").written  # → ["RESULT1", "RESULT2"]
    """

    def __init__(
        self,
        accept_values: list[str] = [],
        files: dict[str, dict[str, Any]] = {},
    ):
        self._accept_queue: list[str] = list(accept_values)
        self._files: dict[str, StubFile] = {
            name: StubFile(records=list(f.get("records", [])))
            for name, f in files.items()
        }

    def get_file(self, filename: str) -> StubFile:
        """Get the StubFile for a filename, creating one if absent."""
        if filename not in self._files:
            self._files = {**self._files, filename: StubFile()}
        return self._files[filename]

    def _accept(self, from_device: str) -> Any:
        if self._accept_queue:
            value = self._accept_queue.pop(0)
            logger.info("StubIOProvider ACCEPT from %s → %r", from_device, value)
            return value
        logger.info(
            "StubIOProvider ACCEPT from %s → UNCOMPUTABLE (queue empty)", from_device
        )
        return _UNCOMPUTABLE

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

    def _read_record(self, filename: str, key: str, program: str) -> Any:
        stub = self._files.get(filename)
        if stub and stub.records:
            record = stub.records.pop(0)
            logger.info("StubIOProvider READ %s → %r", filename, record)
            return IOResult(AccessCondition.OK, record)
        logger.info("StubIOProvider READ %s → AT END", filename)
        return IOResult(AccessCondition.END_OF_FILE, None)

    def _write_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        stub = self.get_file(filename)
        stub.written.append(data)
        logger.info("StubIOProvider WRITE %s ← %r", filename, data)
        return IOResult(AccessCondition.OK, None)

    def _rewrite_record(
        self, filename: str, data: str, key: str, program: str
    ) -> IOResult:
        stub = self.get_file(filename)
        if stub.written:
            stub.written[-1] = data
        else:
            stub.written.append(data)
        logger.info("StubIOProvider REWRITE %s ← %r", filename, data)
        return IOResult(AccessCondition.OK, None)

    def _start_file(
        self, filename: str, key: str, relop: str, program: str
    ) -> IOResult:
        logger.info(
            "StubIOProvider START %s key=%s relop=%s (no-op)", filename, key, relop
        )
        return IOResult(AccessCondition.OK, None)

    def _delete_record(self, filename: str, key: str, program: str) -> IOResult:
        stub = self._files.get(filename)
        if stub and stub.records:
            removed = stub.records.pop(0)
            logger.info("StubIOProvider DELETE %s → removed %r", filename, removed)
        else:
            logger.info("StubIOProvider DELETE %s → no records", filename)
        return IOResult(AccessCondition.OK, None)
