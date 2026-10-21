# pyright: standard
"""A family of machine instructions implemented and tested together, delivered in one wave."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpcodeUnit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    title: str
    wave: int
    mnemonics: tuple[str, ...]
