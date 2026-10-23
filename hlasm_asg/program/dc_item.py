# pyright: standard
"""One operand of a DC statement or literal."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.nominal import Nominal


class DcItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str
    extension: str
    duplication: int
    length: int
    length_unit: LengthUnit
    explicit_length: bool
    scale: int
    exponent: int
    offset: int
    bit_offset: int
    nominal: Nominal
