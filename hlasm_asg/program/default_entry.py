# pyright: standard
"""END named no entry point; the run enters the first CSECT."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DefaultEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["DEFAULT"]
