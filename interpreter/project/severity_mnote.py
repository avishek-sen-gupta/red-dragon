# pyright: standard
"""A unit diagnostic an MNOTE raised with a severity code, with its text."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeverityMnote:
    level: int
    text: str
