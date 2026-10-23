# pyright: standard
"""What an HLASM program's compiled files depend on besides its source; the assembly clock is not among them."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hlasm_asg.assembly_input import AssemblyInput
from interpreter.project.source_file import SourceFile


def _members(directory: Path) -> list[tuple[str, str]]:
    return [
        (str(f), hashlib.sha256(f.read_bytes()).hexdigest())
        for f in sorted(directory.iterdir())
        if f.is_file()
    ]


@dataclass(frozen=True)
class HlasmLoweringSettings:
    syslib_dirs: Sequence[Path]
    bridge_identity: str
    names: Mapping[AssemblyInput, str]

    def artifact(self, program: SourceFile, work_dir: Path, kind: str) -> Path:
        return (
            work_dir / f"{program.path.stem}-{self._digest(program.source)}.{kind}.json"
        )

    def _digest(self, source: bytes) -> str:
        settings = json.dumps(
            {
                "syslib_dirs": [str(d) for d in self.syslib_dirs],
                "syslib_members": [m for d in self.syslib_dirs for m in _members(d)],
                "bridge": self.bridge_identity,
                "names": sorted(
                    (name.name, value) for name, value in self.names.items()
                ),
            }
        )
        return hashlib.sha256(source + b"\0" + settings.encode("utf-8")).hexdigest()
