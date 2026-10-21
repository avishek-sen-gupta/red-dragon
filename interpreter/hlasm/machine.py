# pyright: standard
"""Run-unit start-up IR for the z/Architecture machine state: GPRs, CC and program mask."""

from interpreter.hlasm.hlasm_constants import (
    CC_VAR,
    GPR_BYTES,
    GPR_COUNT,
    GPRS_VAR,
    INITIAL_CC,
    INITIAL_PROGRAM_MASK,
    PROGRAM_MASK_VAR,
)
from interpreter.instructions import AllocRegion, Const, InstructionBase, StoreVar
from interpreter.register import Register

_GPRS_SIZE = Register("%hlasm_machine_gprs_size")
_GPRS = Register("%hlasm_machine_gprs")
_CC = Register("%hlasm_machine_cc")
_PROGRAM_MASK = Register("%hlasm_machine_pm")


def machine_allocation() -> tuple[InstructionBase, ...]:
    return (
        Const.int_(_GPRS_SIZE, GPR_COUNT * GPR_BYTES),
        AllocRegion(result_reg=_GPRS, size_reg=_GPRS_SIZE),
        StoreVar(name=GPRS_VAR, value_reg=_GPRS),
        Const.int_(_CC, INITIAL_CC),
        StoreVar(name=CC_VAR, value_reg=_CC),
        Const.int_(_PROGRAM_MASK, INITIAL_PROGRAM_MASK),
        StoreVar(name=PROGRAM_MASK_VAR, value_reg=_PROGRAM_MASK),
    )
