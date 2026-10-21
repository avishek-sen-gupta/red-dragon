# pyright: standard
"""A machine instruction with resolved operands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.origin import Origin


class MachineStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["MACHINE"]
    section: str
    offset: int
    label: str
    mnemonic: str
    base_mnemonic: str
    format: str
    length: int
    operands: tuple[Operand, ...]
    origin: Origin
