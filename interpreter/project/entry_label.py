# pyright: standard
"""An object module's LD record: a name ENTRY exports, at an offset in one of the module's sections."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryLabel:
    name: str
    section: str
    offset: int
