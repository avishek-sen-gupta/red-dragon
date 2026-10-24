# pyright: standard
"""A constant written in the open-code source."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InOpenCode:
    pass
