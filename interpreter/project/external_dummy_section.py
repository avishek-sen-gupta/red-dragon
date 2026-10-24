# pyright: standard
"""An object module's PR/XD record: an external dummy section's length and alignment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalDummySection:
    name: str
    length: int
    alignment: int
