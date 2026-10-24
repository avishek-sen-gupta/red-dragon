# pyright: standard
"""An external dummy section the program defines (DXD) or names in a Q-constant (DSECT): its length and alignment."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExternalDummy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    length: int
    alignment: int
