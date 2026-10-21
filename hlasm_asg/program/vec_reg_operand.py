# pyright: standard
"""A vector register number."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class VecRegOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["VEC_REG"]
    value: int
