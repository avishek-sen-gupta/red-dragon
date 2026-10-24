# pyright: standard
"""An unresolved WXTRN, which the binder resolves to zero."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeakZero:
    name: str
