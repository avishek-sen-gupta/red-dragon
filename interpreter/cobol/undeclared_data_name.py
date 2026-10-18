"""A data name that no DATA DIVISION section of the program declares."""

from __future__ import annotations


class UndeclaredDataName(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Field {name!r} not found in any DATA DIVISION section")
        self.name = name
