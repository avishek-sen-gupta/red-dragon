# pyright: standard
"""An object module's WX record: a name WXTRN refers to, which resolves to zero when nothing defines it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeakReference:
    name: str
