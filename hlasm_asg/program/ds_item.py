# pyright: standard
"""One operand of a DS statement."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str
    extension: str
    duplication: int
    length: int
    explicit_length: bool
