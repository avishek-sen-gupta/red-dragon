# pyright: standard
"""A unit diagnostic an MNOTE raised with a severity code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeverityMnote:
    level: int
