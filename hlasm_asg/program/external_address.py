# pyright: standard
"""An address constant naming an external symbol, plus an offset from it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExternalAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["EXTERNAL"]
    name: str
    offset: int
