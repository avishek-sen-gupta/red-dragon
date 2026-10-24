# pyright: standard
"""A name the binder resolved to an offset in a section of a module."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlacedName:
    module: str
    section: str
    offset: int
