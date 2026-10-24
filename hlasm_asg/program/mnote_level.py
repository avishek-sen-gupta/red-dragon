# pyright: standard
"""An MNOTE written with a severity code, 0 to 255."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MnoteLevel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["LEVEL"]
    level: int
