# pyright: standard
"""A DD definition's RECFM, as the DCBRECFM byte it fills: F, FB, V or VB, or none given."""

from enum import IntEnum


class RecordFormat(IntEnum):
    UNSPECIFIED = 0
    F = 0x80
    FB = 0x90
    V = 0x40
    VB = 0x50
