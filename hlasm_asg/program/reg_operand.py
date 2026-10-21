# pyright: standard
"""A general register number."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RegOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["REG"]
    value: int
