# pyright: standard
"""Injectable I/O provider for COBOL statement execution.

Provides a pluggable strategy for COBOL I/O operations (ACCEPT, READ, WRITE,
OPEN, CLOSE) during symbolic execution. Similar to UnresolvedCallResolver,
this is injected via VMConfig and accessed by the executor for __cobol_*
CALL_FUNCTION dispatch.

Two implementations:
- NullIOProvider: returns UNCOMPUTABLE for READ; IOResult("00", None) for all other ops.
- StubIOProvider: returns queued test data for concrete execution without files.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


@dataclass(frozen=True)
class IOResult:
    """Structured return value for all CobolIOProvider I/O methods.

    status: COBOL file status code ("00"=success, "10"=AT END, "22"=dup key,
            "23"=key not found, "35"=file not found, "47"=not open).
    data:   Populated on successful READ; None for write-side verbs.
    """

    status: str
    data: str | None


# Dispatch table mapping __cobol_* function names to provider method names.
_COBOL_IO_DISPATCH: dict[FuncName, str] = {
    FuncName("__cobol_accept"): "_accept",
    FuncName("__cobol_open_file"): "_open_file",
    FuncName("__cobol_close_file"): "_close_file",
    FuncName("__cobol_read_record"): "_read_record",
    FuncName("__cobol_write_record"): "_write_record",
    FuncName("__cobol_rewrite_record"): "_rewrite_record",
    FuncName("__cobol_start_file"): "_start_file",
    FuncName("__cobol_delete_record"): "_delete_record",
    FuncName("__cobol_io_status"): "_io_status",
    FuncName("__cobol_io_data"): "_io_data",
    FuncName("__cobol_file_open_mode"): "_open_mode",
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

    def _io_status(self, raw: Any) -> Any:
        """Extract COBOL file status code from an IOResult."""
        if isinstance(raw, IOResult):
            return raw.status
        return _UNCOMPUTABLE

    def _io_data(self, raw: Any) -> Any:
        """Extract record data from an IOResult (empty string if None)."""
        if isinstance(raw, IOResult):
            return raw.data or ""
        return _UNCOMPUTABLE

    def _open_mode(self, filename: Any) -> Any:
        """Current OPEN mode of a file ("INPUT"/"OUTPUT"/"I-O"/"EXTEND"), "" if closed."""
        return ""

    @abstractmethod
    def _accept(
        self, from_device: str
    ) -> Any:  # Any: str | _Uncomputable — VM I/O boundary
        """ACCEPT — read input from a device (e.g. CONSOLE)."""
        ...

    @abstractmethod
    def _open_file(
        self,
        filename: str,
        mode: str,
        record_length: int,
        organization: str,
        key_offset: int,
        key_length: int,
    ) -> IOResult:
        """OPEN file in given mode (INPUT/OUTPUT/I-O/EXTEND)."""
        ...

    @abstractmethod
    def _close_file(self, filename: str) -> IOResult:
        """CLOSE file."""
        ...

    @abstractmethod
    def _read_record(
        self, filename: str, key: str
    ) -> Any:  # Any: IOResult | _Uncomputable
        """READ — get next record from file."""
        ...

    @abstractmethod
    def _write_record(self, filename: str, data: str) -> IOResult:
        """WRITE — write a record to file."""
        ...

    @abstractmethod
    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        """REWRITE — replace the last-read record in file."""
        ...

    @abstractmethod
    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        """START — position file at key for sequential reading."""
        ...

    @abstractmethod
    def _delete_record(self, filename: str) -> IOResult:
        """DELETE — remove the last-read record from file."""
        ...


@dataclass
class StubFile:
    """In-memory file stub for testing — holds read records and captures writes."""

    records: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    is_open: bool = False


class NullIOProvider(CobolIOProvider):
    """Default provider — returns UNCOMPUTABLE for READ, IOResult("00", None) for all other ops."""

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
        return IOResult("00", None)

    def _close_file(self, filename: str) -> IOResult:
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str) -> Any:
        return _UNCOMPUTABLE

    def _write_record(self, filename: str, data: str) -> IOResult:
        return IOResult("00", None)

    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        return IOResult("00", None)

    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        return IOResult("00", None)

    def _delete_record(self, filename: str) -> IOResult:
        return IOResult("00", None)


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
            self._files[filename] = StubFile()
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

    def _open_file(
        self,
        filename: str,
        mode: str,
        record_length: int,
        organization: str,
        key_offset: int,
        key_length: int,
    ) -> IOResult:
        stub = self.get_file(filename)
        stub.is_open = True
        logger.info("StubIOProvider OPEN %s mode=%s", filename, mode)
        return IOResult("00", None)

    def _close_file(self, filename: str) -> IOResult:
        if filename in self._files:
            self._files[filename].is_open = False
        logger.info("StubIOProvider CLOSE %s", filename)
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str) -> Any:
        stub = self._files.get(filename)
        if stub and stub.records:
            record = stub.records.pop(0)
            logger.info("StubIOProvider READ %s → %r", filename, record)
            return IOResult("00", record)
        logger.info("StubIOProvider READ %s → AT END", filename)
        return IOResult("10", None)

    def _write_record(self, filename: str, data: str) -> IOResult:
        stub = self.get_file(filename)
        stub.written.append(data)
        logger.info("StubIOProvider WRITE %s ← %r", filename, data)
        return IOResult("00", None)

    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        stub = self.get_file(filename)
        if stub.written:
            stub.written[-1] = data
        else:
            stub.written.append(data)
        logger.info("StubIOProvider REWRITE %s ← %r", filename, data)
        return IOResult("00", None)

    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        logger.info(
            "StubIOProvider START %s key=%s relop=%s (no-op)", filename, key, relop
        )
        return IOResult("00", None)

    def _delete_record(self, filename: str) -> IOResult:
        stub = self._files.get(filename)
        if stub and stub.records:
            removed = stub.records.pop(0)
            logger.info("StubIOProvider DELETE %s → removed %r", filename, removed)
        else:
            logger.info("StubIOProvider DELETE %s → no records", filename)
        return IOResult("00", None)
