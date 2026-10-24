# pyright: standard
"""A line of a source or library member that a unit's diagnostic names."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticPlace:
    file: str
    line: int
