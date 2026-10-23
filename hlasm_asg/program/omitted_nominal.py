# pyright: standard
"""A DC operand written without a nominal value, as DC 0F is."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class OmittedNominal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["OMITTED"]
