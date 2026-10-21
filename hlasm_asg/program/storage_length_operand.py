# pyright: standard
"""A D(L,B) storage operand of an SS format; length as written."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StorageLengthOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["STORAGE_LENGTH"]
    displacement: int
    length: int
    base: int
