"""What a COBOL program's compiled files depend on besides its source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cobol_asg.lp import LP
from interpreter.project.source_file import SourceFile


@dataclass(frozen=True)
class LoweringSettings:
    lp: LP
    extension_names: tuple[str, ...]
    tolerant: bool
    copybook_dirs: tuple[Path, ...]

    def artifact(self, program: SourceFile, work_dir: Path, kind: str) -> Path:
        return (
            work_dir / f"{program.path.stem}-{self._digest(program.source)}.{kind}.json"
        )

    def _digest(self, source: bytes) -> str:
        settings = json.dumps(
            [
                self.lp.value,
                list(self.extension_names),
                self.tolerant,
                [str(d) for d in self.copybook_dirs],
            ]
        )
        return hashlib.sha256(source + b"\0" + settings.encode("utf-8")).hexdigest()
