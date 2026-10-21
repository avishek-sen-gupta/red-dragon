# pyright: standard
"""The kind of a section as the bridge names it."""

from __future__ import annotations

from enum import StrEnum


class SectionKind(StrEnum):
    CSECT = "CSECT"
    DSECT = "DSECT"
    COM = "COM"
    RSECT = "RSECT"
