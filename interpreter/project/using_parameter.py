# pyright: standard
"""One position of a COBOL program's PROCEDURE DIVISION USING: how it is received and its byte length."""

from dataclasses import dataclass

from interpreter.project.argument_mode import ArgumentMode


@dataclass(frozen=True)
class UsingParameter:
    mode: ArgumentMode
    length: int
