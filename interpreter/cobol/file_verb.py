"""One COBOL file verb: its logic-error checks before and after its driver action,
the action, and the file state it leaves."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.cobol.access_result import AccessResult
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.open_file import OpenFile


def _permitted(file: OpenFile, result: AccessResult) -> FileLogicStatus:
    return FileLogicStatus.PERMITTED


@dataclass(frozen=True)
class FileVerb:
    check: Callable[[OpenFile], FileLogicStatus]
    action: Callable[[OpenFile], AccessResult]
    after: Callable[[OpenFile, AccessResult], OpenFile]
    outcome: Callable[[OpenFile, AccessResult], FileLogicStatus] = _permitted
