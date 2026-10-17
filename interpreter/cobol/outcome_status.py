"""The FILE STATUS each driver outcome reports (ANSI X3.23-1985 VI-1.3.5, the I-O status;
IBM Enterprise COBOL LR, file status key values), most frequent first."""

from __future__ import annotations

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_logic_status import FileLogicStatus

OUTCOME_STATUS: tuple[tuple[AccessCondition, FileLogicStatus], ...] = (
    (AccessCondition.OK, FileLogicStatus.PERMITTED),
    (AccessCondition.END_OF_FILE, FileLogicStatus.AT_END),
    (AccessCondition.NOT_FOUND, FileLogicStatus.NOT_FOUND),
    (AccessCondition.DUPLICATE_KEY, FileLogicStatus.DUPLICATE_KEY),
    (AccessCondition.DUPLICATES_FOLLOW, FileLogicStatus.DUPLICATES_FOLLOW),
    (AccessCondition.FILE_NOT_FOUND, FileLogicStatus.FILE_ABSENT),
    (AccessCondition.ATTRIBUTE_CONFLICT, FileLogicStatus.ATTRIBUTE_CONFLICT),
    (
        AccessCondition.OPEN_MODE_NOT_SUPPORTED,
        FileLogicStatus.OPEN_MODE_NOT_SUPPORTED,
    ),
    (AccessCondition.BOUNDARY_VIOLATION, FileLogicStatus.RECORD_SIZE_VIOLATION),
    (AccessCondition.NOT_OPEN, FileLogicStatus.READ_NOT_PERMITTED),
    (AccessCondition.WRITE_NOT_PERMITTED, FileLogicStatus.WRITE_NOT_PERMITTED),
)
