# pyright: standard
"""Outcome of a floating-point comparison; the value is the condition code."""

from enum import Enum


class Comparison(Enum):
    EQUAL = 0
    LOW = 1
    HIGH = 2
    UNORDERED = 3
