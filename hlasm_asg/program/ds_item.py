# pyright: standard
"""One operand of a DS statement."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.length_unit import LengthUnit


class DsItem(BaseModel):
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
