"""Neutral access-method outcome — the engine's shared, consumer-agnostic result.

Carries the underlying access-method *condition*, NOT any consumer's status
vocabulary (no COBOL FILE STATUS, no CICS EIBRESP). Each consumer adapter maps
AccessCondition to its own vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccessCondition(Enum):
    OK = "OK"
    END_OF_FILE = "END_OF_FILE"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    NOT_OPEN = "NOT_OPEN"
    WRITE_NOT_PERMITTED = "WRITE_NOT_PERMITTED"


@dataclass(frozen=True)
class AccessResult:
    condition: AccessCondition
    data: bytes | None = None
