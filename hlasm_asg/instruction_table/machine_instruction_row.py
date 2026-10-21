# pyright: standard
"""A machine instruction: an opcode in its own right, with no base."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.architecture_level import ArchitectureLevel
from hlasm_asg.instruction_table.operand import Operand
from hlasm_asg.instruction_table.privilege import Privilege


class MachineInstructionRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mnemonic: str
    format: str
    privileged: Privilege
    arch: ArchitectureLevel
    operands: tuple[Operand, ...]
    base: None
    transforms: tuple[()]
