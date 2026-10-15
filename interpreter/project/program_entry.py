# pyright: standard
"""Enter a linked image at the program of this name."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramEntry:
    name: str
