# pyright: standard
"""An external symbol the program refers to and how strongly."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.external_kind import ExternalKind


class ExternalSymbol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: ExternalKind
