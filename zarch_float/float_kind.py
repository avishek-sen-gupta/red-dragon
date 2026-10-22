# pyright: standard
"""The data class of an IEEE (BFP or DFP) operand."""

from enum import Enum


class FloatKind(Enum):
    ZERO = "zero"
    FINITE = "finite"
    INFINITY = "infinity"
    QNAN = "qnan"
    SNAN = "snan"
