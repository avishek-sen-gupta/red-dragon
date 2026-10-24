# pyright: standard
"""The name an RLD record relocates by: a section, an ENTRY, an external symbol or an external dummy section."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RelocationName:
    name: str
