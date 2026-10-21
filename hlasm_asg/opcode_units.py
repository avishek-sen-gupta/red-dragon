# pyright: standard
"""The partition of every problem-state machine instruction into opcode units."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.opcode_unit import OpcodeUnit


class OpcodeUnits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    units: tuple[OpcodeUnit, ...]
