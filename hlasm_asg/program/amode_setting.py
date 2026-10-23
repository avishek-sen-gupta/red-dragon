# pyright: standard
"""An AMODE statement: the name it qualifies and the mode."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.addressing_mode import AddressingMode


class AmodeSetting(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    mode: AddressingMode
