# pyright: standard
"""The record operations a file provider serves: declare, open, close, read, write, rewrite,
start and delete, each answering an IOResult, routed by the executor from CALL_FUNCTION.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from interpreter.data_value import DataRecord
from interpreter.func_name import FuncName
from interpreter.record_io.access_result import AccessCondition
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


@dataclass(frozen=True)
class IOResult:
    """Structured return value for all provider I/O methods.

    condition: the driver's outcome; the lowering's IR maps it to its language's status.
    data:      Populated on successful READ; None for write-side verbs.
    """

    condition: AccessCondition
    data: str | None
    record_number: int = 0


RECORD_OPERATIONS: Mapping[FuncName, str] = MappingProxyType(
    {
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
    }
)


class RecordIOProvider(ABC):
    """Abstract base for record I/O during symbolic execution.

    The executor calls handle_call(func_name, args) for any CALL_FUNCTION the provider
    dispatches. Implementations decide whether to return concrete data or UNCOMPUTABLE
    (which the executor wraps as symbolic).
    """

    operations: Mapping[FuncName, str] = RECORD_OPERATIONS

    def dispatch(self, name: FuncName) -> str | None:
        return self.operations.get(name)

    def handle_call(
        self, func_name: FuncName, args: list[TypedValue]
    ) -> Any:  # Any: str | int | IOResult | _Uncomputable — VM I/O boundary
        """Route a call to the appropriate method.

        Returns a concrete value or UNCOMPUTABLE if unhandled.
        """
        method_name = self.dispatch(func_name)
        if method_name is None:
            logger.debug("RecordIOProvider: unknown func %s", func_name)
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
        self, filename: str, locator: str, program: str
    ) -> Any:  # Any: IOResult | _Uncomputable
        """READ — get next record from file."""
        ...

    @abstractmethod
    def _write_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        """WRITE — write a record to file, at relative record number ``locator`` if given."""
        ...

    @abstractmethod
    def _rewrite_record(
        self, filename: str, data: str, locator: str, program: str
    ) -> IOResult:
        """REWRITE — replace the record numbered ``locator``, or the last-read one."""
        ...

    @abstractmethod
    def _start_file(
        self, filename: str, locator: str, relop: str, program: str
    ) -> IOResult:
        """START — position file at the locator for sequential reading."""
        ...

    @abstractmethod
    def _delete_record(self, filename: str, locator: str, program: str) -> IOResult:
        """DELETE — remove the record ``locator`` names, or the last-read record
        when ``locator`` is empty (sequential access)."""
        ...
