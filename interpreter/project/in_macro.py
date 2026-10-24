# pyright: standard
"""A constant that a macro generated, named by the macro."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InMacro:
    name: str
