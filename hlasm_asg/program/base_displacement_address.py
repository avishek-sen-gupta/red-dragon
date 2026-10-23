# pyright: standard
"""An S-type address constant: a base register and displacement, resolved through USING."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class BaseDisplacementAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["BASE_DISPLACEMENT"]
    base: int
    displacement: int
