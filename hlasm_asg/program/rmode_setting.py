# pyright: standard
"""An RMODE statement: the name it qualifies and the mode."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.residency_mode import ResidencyMode


class RmodeSetting(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    mode: ResidencyMode
