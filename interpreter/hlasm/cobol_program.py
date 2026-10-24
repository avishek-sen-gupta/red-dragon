# pyright: standard
"""A COBOL program of a mixed image as the binder sees it: its PROGRAM-ID, the unit file it came from and its USING signature."""

from dataclasses import dataclass

from interpreter.project.using_parameter import UsingParameter


@dataclass(frozen=True)
class CobolProgram:
    name: str
    file: str
    using: tuple[UsingParameter, ...]
