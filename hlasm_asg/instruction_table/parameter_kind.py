# pyright: standard
"""What a sub-field inside a displacement operand denotes."""

from __future__ import annotations

from enum import StrEnum


class ParameterKind(StrEnum):
    BASE = "BASE"
    IDX_REG = "IDX_REG"
    LENGTH = "LENGTH"
    NONE = "NONE"
    REG = "REG"
    VEC_REG = "VEC_REG"
