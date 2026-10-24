# pyright: standard
"""An object module's SD record: a control section and its length; private code is named ""."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlSection:
    name: str
    length: int
