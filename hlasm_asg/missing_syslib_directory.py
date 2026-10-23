# pyright: standard
"""Raised when a SYSLIB directory does not exist, so its macros cannot silently go missing."""

from __future__ import annotations

from pathlib import Path


class MissingSyslibDirectory(Exception):
    def __init__(self, directory: Path):
        super().__init__(f"SYSLIB directory {directory} does not exist")
        self.directory = directory
