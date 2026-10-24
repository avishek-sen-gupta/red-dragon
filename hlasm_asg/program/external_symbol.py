# pyright: standard
"""An external symbol the program refers to, how strongly, and the open-code line of its EXTRN or WXTRN, else of its first use."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.external_kind import ExternalKind


class ExternalSymbol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: ExternalKind
    line: int
