# pyright: standard
"""A floating-point format as floating-point registers hold it: the image width selects the register access."""

from typing import Protocol


class FprLayout(Protocol):
    width: int
