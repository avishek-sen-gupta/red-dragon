# pyright: standard
"""A far-branch owner: an HLASM module of the image."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleOwner:
    module: str
