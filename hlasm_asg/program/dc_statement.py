# pyright: standard
"""A DC statement."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.origin import Origin


class DcStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["DC"]
    section: str
    offset: int
    label: str
    mnemonic: Literal["DC"]
    items: tuple[DcItem, ...]
    origin: Origin
