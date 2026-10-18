"""CopybookLibrary — a COBOL library a COPY names with OF or IN, and the directory that holds it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopybookLibrary:
    name: str
    directory: Path
