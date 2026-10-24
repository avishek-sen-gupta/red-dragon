# pyright: standard
"""An external dummy section bound into the pseudo-register area: its offset there and its merged length."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PseudoRegister:
    offset: int
    length: int
