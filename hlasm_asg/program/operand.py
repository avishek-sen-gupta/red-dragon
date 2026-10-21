# pyright: standard
"""A resolved operand of a machine instruction."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from hlasm_asg.program.vec_reg_operand import VecRegOperand

Operand = Annotated[
    RegOperand
    | MaskOperand
    | ImmOperand
    | VecRegOperand
    | RelocImmOperand
    | StorageOperand
    | StorageLengthOperand,
    Field(discriminator="kind"),
]
