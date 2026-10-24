# pyright: standard
"""Whether a relocatable term of a complex-relocatable value names a section of the program or an external symbol."""

from __future__ import annotations

from enum import StrEnum


class TermKind(StrEnum):
    SECTION = "SECTION"
    EXTERNAL = "EXTERNAL"
