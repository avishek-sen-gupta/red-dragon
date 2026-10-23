# pyright: standard
"""A che4z diagnostic with its code, severity and source position."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.related_location import RelatedLocation
from hlasm_asg.program.severity import Severity


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Severity
    message: str
    file: str
    line: int
    related: tuple[RelatedLocation, ...]
