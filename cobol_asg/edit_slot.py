"""Whether a numeric edit picture's position can hold the floating insertion symbol, and when."""

from __future__ import annotations

from enum import Enum


class EditSlot(Enum):
    """NONE: never. BEFORE_DIGIT: when the next digit is the first significant
    one. FLOAT_END: when no floating digit is the first significant one."""

    NONE = "none"
    BEFORE_DIGIT = "before_digit"
    FLOAT_END = "float_end"
