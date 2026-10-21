# pyright: standard
"""An extended mnemonic: a base machine instruction with some operands fixed."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.architecture_level import ArchitectureLevel
from hlasm_asg.instruction_table.operand import Operand
from hlasm_asg.instruction_table.privilege import Privilege
from hlasm_asg.instruction_table.transform import Transform


class MnemonicRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mnemonic: str
    format: str
    privileged: Privilege
    arch: ArchitectureLevel
    operands: tuple[Operand, ...]
    base: str
    transforms: tuple[Transform, ...]
