# pyright: standard
"""An address constant that is an absolute number."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AbsAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["ABS"]
    value: int
