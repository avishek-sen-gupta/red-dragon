# pyright: standard
"""An object module's ER record: a name EXTRN or a V-constant refers to, and the line that declared or first used it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalReference:
    name: str
    line: int
