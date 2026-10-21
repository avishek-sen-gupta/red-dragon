# pyright: standard
"""A condition-mask value."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MaskOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["MASK"]
    value: int
