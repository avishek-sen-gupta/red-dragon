# pyright: standard
"""A unit diagnostic that encoding a constant raised: the constant as written, what its conversion warns of, and where it was written."""

from dataclasses import dataclass

from interpreter.project.constant_source import ConstantSource
from interpreter.project.dc_warning_kind import DcWarningKind


@dataclass(frozen=True)
class ConstantDiagnostic:
    constant: str
    warning: DcWarningKind
    source: ConstantSource
