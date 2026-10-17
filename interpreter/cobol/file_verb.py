"""One COBOL file verb: its logic-error check, its driver action and the position it leaves."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.cobol.access_result import AccessCondition, AccessResult
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.open_file import OpenFile


@dataclass(frozen=True)
class FileVerb:
    check: Callable[[OpenFile], FileLogicStatus]
    action: Callable[[OpenFile], AccessResult]
    after: Callable[[OpenFile, AccessCondition], OpenFile]
