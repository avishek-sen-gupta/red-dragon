# pyright: standard
"""What a type-extended floating-point DC conversion warns of (Language Reference pp. 127, 156-157): a value past MAX, one below the normal range and rounded, or one rounded."""

from enum import Enum


class DcWarningKind(Enum):
    OVERFLOW = "overflow"
    UNDERFLOW = "underflow"
    INEXACT = "inexact"
