# pyright: standard
"""An object module's ER record: a name EXTRN or a V-constant refers to."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalReference:
    name: str
