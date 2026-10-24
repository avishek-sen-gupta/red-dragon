# pyright: standard
"""Whether an external symbol was declared by EXTRN (or named by a V-constant) or by WXTRN."""

from __future__ import annotations

from enum import StrEnum


class ExternalKind(StrEnum):
    EXTRN = "EXTRN"
    WXTRN = "WXTRN"
