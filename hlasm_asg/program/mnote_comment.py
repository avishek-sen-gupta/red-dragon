# pyright: standard
"""An MNOTE written as a comment: MNOTE *,'text' or MNOTE 'text'."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MnoteComment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["COMMENT"]
