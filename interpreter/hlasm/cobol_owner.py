# pyright: standard
"""A far-branch owner: a COBOL program of a mixed image, called with the arguments its USING signature reads from the R1 list."""

from dataclasses import dataclass

from interpreter.hlasm.cobol_program import CobolProgram


@dataclass(frozen=True)
class CobolOwner:
    program: CobolProgram
