# pyright: standard
"""The floating-point special values a DC nominal can name (Language Reference p. 157)."""

from enum import Enum


class FloatSpecialValue(Enum):
    INF = "INF"
    NAN = "NAN"
    QNAN = "QNAN"
    SNAN = "SNAN"
    MAX = "MAX"
    MIN = "MIN"
    DMIN = "DMIN"
