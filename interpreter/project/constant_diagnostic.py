# pyright: standard
"""A unit diagnostic that encoding a constant raised."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstantDiagnostic:
    pass
