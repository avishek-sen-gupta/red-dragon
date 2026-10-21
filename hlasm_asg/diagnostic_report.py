# pyright: standard
"""The diagnostics the bridge prints to stderr when it refuses a source."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.diagnostic import Diagnostic


class DiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    diagnostics: tuple[Diagnostic, ...]
