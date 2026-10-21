# pyright: standard
"""The entry point END names."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class NamedEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["NAMED"]
    name: str
