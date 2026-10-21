# pyright: standard
"""A relative-immediate target: a section and an offset in it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RelocImmOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["RELOC_IMM"]
    section: str
    offset: int
