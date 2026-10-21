# pyright: standard
"""A parser that writes the HLASM program JSON of a source to a file and reads it back."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hlasm_asg.program.hlasm_program import HlasmProgram


class HlasmAstParser(Protocol):
    def parse_to_file(self, source: bytes, out_path: Path) -> Path: ...

    def read(self, path: Path) -> HlasmProgram: ...
