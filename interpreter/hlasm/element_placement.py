# pyright: standard
"""Where a zero-extended vector load puts its element: the element's width in bytes and its left shift within the 128-bit register."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ElementPlacement:
    width: int
    shift: int
