# pyright: standard
"""One frame of the macro call stack che4z attaches to a diagnostic."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RelatedLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str
    line: int
