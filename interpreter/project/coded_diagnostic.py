# pyright: standard
"""A unit diagnostic the assembler raised under a message code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CodedDiagnostic:
    code: str
