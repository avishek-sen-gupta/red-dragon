# pyright: standard
"""The severity che4z gives a diagnostic."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    HINT = "HINT"
    UNSPECIFIED = "UNSPECIFIED"
