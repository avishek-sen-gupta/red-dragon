# pyright: standard
"""A far-branch owner: an EXTRN nothing in the image defines, called by its name."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnresolvedOwner:
    name: str
