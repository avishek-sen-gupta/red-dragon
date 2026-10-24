# pyright: standard
"""An object module's CM record: a common section, merged by name across the image at its largest length."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommonSection:
    name: str
    length: int
