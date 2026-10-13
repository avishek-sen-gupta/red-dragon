"""One source file handed to a compiler: its path and its bytes, already read."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    path: Path
    source: bytes
