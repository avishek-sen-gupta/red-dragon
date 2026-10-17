"""Where a COBOL file's position indicator stands after its last I-O statement."""

from __future__ import annotations

from enum import Enum


class FilePosition(Enum):
    NO_CURRENT_RECORD = "NO_CURRENT_RECORD"
    CURRENT_RECORD = "CURRENT_RECORD"
    AT_END = "AT_END"
