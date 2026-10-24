# pyright: standard
"""An object module's END record naming its entry point, and where that name is."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NamedEnd:
    name: str
    section: str
    offset: int
