"""The ANSI X3.23-1985 I-O statuses the lowering's file IR sets or tests."""

from __future__ import annotations

from enum import Enum


class FileLogicStatus(Enum):
    PERMITTED = "00"
    DUPLICATES_FOLLOW = "02"
    OPTIONAL_ABSENT = "05"
    AT_END = "10"
    NOT_FOUND = "23"
    FILE_ABSENT = "35"
    OPEN_MODE_NOT_SUPPORTED = "37"
    ATTRIBUTE_CONFLICT = "39"
    RELATIVE_KEY_TOO_SMALL = "14"
    SEQUENCE_ERROR = "21"
    DUPLICATE_KEY = "22"
    BOUNDARY_VIOLATION = "24"
    CLOSED_WITH_LOCK = "38"
    RECORD_SIZE_VIOLATION = "44"
    ALREADY_OPEN = "41"
    NOT_OPEN = "42"
    NO_CURRENT_RECORD = "43"
    NO_NEXT_RECORD = "46"
    READ_NOT_PERMITTED = "47"
    WRITE_NOT_PERMITTED = "48"
    UPDATE_NOT_PERMITTED = "49"
