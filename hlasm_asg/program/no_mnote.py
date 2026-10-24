# pyright: standard
"""A diagnostic that no MNOTE statement raised."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class NoMnote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["NONE"]
