# pyright: standard
"""Whether a relocation adds its target's value to the field or subtracts it."""

from enum import StrEnum


class RelocationSign(StrEnum):
    PLUS = "PLUS"
    MINUS = "MINUS"
