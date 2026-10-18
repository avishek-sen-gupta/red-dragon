# pyright: standard
"""The attribute a PROGRAM-ID paragraph gives its program, as the bridge names it."""

from enum import StrEnum


class ProgramAttribute(StrEnum):
    """NONE when the PROGRAM-ID paragraph writes no attribute."""

    NONE = ""
    COMMON = "COMMON"
    INITIAL = "INITIAL"
    LIBRARY = "LIBRARY"
    DEFINITION = "DEFINITION"
    RECURSIVE = "RECURSIVE"
