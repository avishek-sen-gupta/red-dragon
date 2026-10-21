# pyright: standard
"""The entry point of an assembly: its name and where it is."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HlasmEntry:
    name: str
    section: str
    offset: int
