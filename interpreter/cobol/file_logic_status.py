"""The ANSI X3.23-1985 I-O status a misused file verb yields, or PERMITTED."""

from __future__ import annotations

from enum import Enum

from interpreter.cobol.io_provider import IOResult


class FileLogicStatus(Enum):
    PERMITTED = "00"
    RELATIVE_KEY_TOO_SMALL = "14"
    SEQUENCE_ERROR = "21"
    CLOSED_WITH_LOCK = "38"
    ALREADY_OPEN = "41"
    NOT_OPEN = "42"
    NO_CURRENT_RECORD = "43"
    NO_NEXT_RECORD = "46"
    READ_NOT_PERMITTED = "47"
    WRITE_NOT_PERMITTED = "48"
    UPDATE_NOT_PERMITTED = "49"

    def result(self) -> IOResult:
        return IOResult(self.value, None)
