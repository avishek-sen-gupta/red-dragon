# pyright: standard
"""A diagnostic below error level that lowering a unit raised, kept in its unit file so a reused unit reports it again."""

from dataclasses import dataclass

from interpreter.project.diagnostic_kind import DiagnosticKind
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity


@dataclass(frozen=True)
class UnitDiagnostic:
    severity: DiagnosticSeverity
    kind: DiagnosticKind
    place: DiagnosticPlace
    stack: tuple[DiagnosticPlace, ...] = ()
