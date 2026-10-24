# pyright: standard
"""An object module's TXT record: bytes at an offset in one of the module's sections."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextRecord:
    section: str
    offset: int
    image: bytes
