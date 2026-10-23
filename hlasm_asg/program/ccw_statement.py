# pyright: standard
"""A CCW, CCW0 or CCW1 statement with its evaluated operands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.address import Address
from hlasm_asg.program.origin import Origin


class CcwStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["CCW"]
    section: str
    offset: int
    label: str
    mnemonic: Literal["CCW", "CCW0", "CCW1"]
    command_code: int
    address: Address
    flags: int
    count: int
    origin: Origin
