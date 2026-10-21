# pyright: standard
"""A symbol whose value is an offset into a section."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RelocSymbol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["RELOC"]
    name: str
    section: str
    offset: int
    type: str
    length: int
