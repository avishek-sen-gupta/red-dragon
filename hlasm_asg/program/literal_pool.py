# pyright: standard
"""A literal and where the assembler placed it."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.dc_item import DcItem


class LiteralPool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str
    offset: int
    item: DcItem
