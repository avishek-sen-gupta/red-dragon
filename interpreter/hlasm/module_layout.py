# pyright: standard
"""Where a module's control sections sit in its region, and the region's length."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleLayout:
    offsets: Mapping[str, int]
    length: int
