# pyright: standard
"""A literal, where the assembler placed it, and the statement that first used it."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.origin import Origin


class LiteralPool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str
    offset: int
    item: DcItem
    origin: Origin
