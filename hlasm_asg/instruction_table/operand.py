# pyright: standard
"""One operand of a machine instruction or extended mnemonic."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.operand_kind import OperandKind
from hlasm_asg.instruction_table.parameter import Parameter


class Operand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: OperandKind
    bits: int
    signed: bool
    first: Parameter
    second: Parameter
    optional: bool
