# pyright: standard
"""A far-branch owner: a COBOL program of a mixed image (red-dragon-6uyp.15 builds these)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CobolOwner:
    program: str
