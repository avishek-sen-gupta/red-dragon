# pyright: standard
"""An immediate value."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ImmOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["IMM"]
    value: int
