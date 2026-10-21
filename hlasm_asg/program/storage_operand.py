# pyright: standard
"""A D(X,B) storage operand."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StorageOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["STORAGE"]
    displacement: int
    index: int
    base: int
