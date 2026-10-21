# pyright: standard
"""A statement written in the open-code source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class OpenCodeOrigin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["OPEN_CODE"]
    file: str
    line: int
