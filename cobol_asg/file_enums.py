# pyright: standard
"""COBOL file I/O enumerations.

All use the str mixin so they can be constructed directly from bridge JSON
strings: ``OpenMode("INPUT")`` and compared with plain string equality.
"""

from __future__ import annotations

from enum import Enum


class OpenMode(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    IO = "I-O"
    EXTEND = "EXTEND"


class FileOrganization(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    INDEXED = "INDEXED"
    RELATIVE = "RELATIVE"


class AccessMode(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    RANDOM = "RANDOM"
    DYNAMIC = "DYNAMIC"


class RecordingMode(Enum):
    """An FD's RECORDING MODE, or NOT_CODED when the FD has none."""

    F = "F"
    V = "V"
    U = "U"
    S = "S"
    NOT_CODED = ""
