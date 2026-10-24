# pyright: standard
"""The target of an RLD record that names nothing: the total length of the external dummy sections (CXD)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NoRelocationTarget:
    pass
