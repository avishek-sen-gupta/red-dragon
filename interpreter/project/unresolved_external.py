# pyright: standard
"""An EXTRN that nothing in the image defines; the binder gives it a stub address."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnresolvedExternal:
    name: str
