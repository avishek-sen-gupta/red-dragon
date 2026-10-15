"""Null object: no work directory was given, so a fresh temporary one is made."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FreshWorkDir:
    """Stands for a new temporary work directory."""


FRESH_WORK_DIR = FreshWorkDir()
