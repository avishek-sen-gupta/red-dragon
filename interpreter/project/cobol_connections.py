# pyright: standard
"""COBOL inter-program connection extraction.

ProgramRef      — identifies a program or copybook by name and optional file path.
Connection      — a directed COPY or CALL relationship between two ProgramRefs.
extract_cobol_connections() — compile a COBOL project and return all connections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import ImportKind


@dataclass(frozen=True)
class ProgramRef:
    """Identifies a COBOL program or copybook."""

    name: str
    file_path: Path | None


@dataclass(frozen=True)
class Connection:
    """A directed COPY or CALL relationship between two COBOL programs."""

    kind: str  # "COPY" or "CALL"
    source: ProgramRef
    target: ProgramRef

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "source_name": self.source.name,
                "source_file": (
                    str(self.source.file_path) if self.source.file_path else None
                ),
                "target_name": self.target.name,
                "target_file": (
                    str(self.target.file_path) if self.target.file_path else None
                ),
            }
        )
