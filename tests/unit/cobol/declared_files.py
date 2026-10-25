"""Opens a file on a provider after declaring its frame, as a program's start-up code does."""

from __future__ import annotations

from interpreter.cobol.io_provider import CobolIOProvider
from interpreter.record_io.file_frame import FileFrame
from interpreter.record_io.io_provider import IOResult

PROGRAM = "P"


def opened(provider: CobolIOProvider, mode: str, frame: FileFrame) -> IOResult:
    provider._declare_file(frame.data(), PROGRAM)
    return provider._open_file(frame.file_name, mode, PROGRAM)
