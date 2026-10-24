# pyright: standard
"""An object module's END record naming no entry point: the module is entered at its first control section."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DefaultEnd:
    section: str
