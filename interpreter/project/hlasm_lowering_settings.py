# pyright: standard
"""What an HLASM program's compiled files depend on besides its source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from interpreter.project.source_file import SourceFile


@dataclass(frozen=True)
class HlasmLoweringSettings:
    syslib_dirs: tuple[str, ...]

    def artifact(self, program: SourceFile, work_dir: Path, kind: str) -> Path:
        return (
            work_dir / f"{program.path.stem}-{self._digest(program.source)}.{kind}.json"
        )

    def _digest(self, source: bytes) -> str:
        settings = json.dumps({"syslib_dirs": list(self.syslib_dirs)})
        return hashlib.sha256(source + b"\0" + settings.encode("utf-8")).hexdigest()
