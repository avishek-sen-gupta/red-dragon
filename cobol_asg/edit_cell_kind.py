"""What one position of a numeric edit picture shows: a fixed character, a sign, a digit, a suppressible digit or an insertion character."""

from __future__ import annotations

from enum import Enum


class EditCellKind(Enum):
    """How a numeric edit picture's position finds its character for a value."""

    FIXED = "fixed"
    SIGN = "sign"
    DIGIT = "digit"
    SUPPRESSED = "suppressed"
    INSERTION = "insertion"
