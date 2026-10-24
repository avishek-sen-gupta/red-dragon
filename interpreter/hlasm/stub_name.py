# pyright: standard
"""An unresolved EXTRN the binder gave a stub address: the index of its stub in the link-allocated range."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StubName:
    name: str
    index: int
