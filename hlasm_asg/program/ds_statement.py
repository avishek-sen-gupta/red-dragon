# pyright: standard
"""A DS statement."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.ds_item import DsItem
from hlasm_asg.program.origin import Origin


class DsStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["DS"]
    section: str
    offset: int
    label: str
    mnemonic: Literal["DS"]
    items: tuple[DsItem, ...]
    origin: Origin
