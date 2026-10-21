# pyright: standard
"""A symbol with an absolute value."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AbsSymbol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["ABS"]
    name: str
    value: int
    type: str
    length: int
