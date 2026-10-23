# pyright: standard
"""A parser that writes the HLASM program JSON of a source to a file and reads it back."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hlasm_asg.assembly_inputs import AssemblyInputs
from hlasm_asg.program.hlasm_program import HlasmProgram


class HlasmAstParser(Protocol):
    @property
    def syslib(self) -> tuple[Path, ...]: ...

    @property
    def identity(self) -> str: ...

    def parse_to_file(
        self, source: bytes, source_name: str, out_path: Path, inputs: AssemblyInputs
    ) -> Path: ...

    def read(self, path: Path) -> HlasmProgram: ...
