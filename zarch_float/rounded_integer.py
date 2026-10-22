# pyright: standard
"""A ratio rounded to an integer magnitude, and how it differs from the ratio."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoundedInteger:
    magnitude: int
    inexact: bool
    incremented: bool
