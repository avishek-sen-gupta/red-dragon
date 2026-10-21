# pyright: standard
"""A nominal value kept as the text between the quotes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StringNominal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["STRING"]
    value: str
