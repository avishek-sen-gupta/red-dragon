# pyright: standard
"""An address constant that is an offset into a section."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RelocAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["RELOC"]
    section: str
    offset: int
