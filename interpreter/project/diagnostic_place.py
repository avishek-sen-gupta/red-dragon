# pyright: standard
"""A line of a source or library member that a unit's diagnostic names."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticPlace:
    file: str
    line: int

    @property
    def text(self) -> str:
        return f"{self.file}:{self.line}"
