# pyright: standard
"""Run-unit start-up IR for the z/Architecture machine state: GPRs, CC, program mask, the last stored clock value and the access registers."""

from interpreter.hlasm.hlasm_constants import (
    ACCESS_REGISTER_BYTES,
    ACCESS_REGISTERS_VAR,
    CC_VAR,
    GPR_BYTES,
    GPR_COUNT,
    GPRS_VAR,
    INITIAL_CC,
    INITIAL_PROGRAM_MASK,
    PROGRAM_MASK_VAR,
    TOD_LAST_VAR,
)
from interpreter.instructions import AllocRegion, Const, InstructionBase, StoreVar
from interpreter.register import Register

_GPRS_SIZE = Register("%hlasm_machine_gprs_size")
_GPRS = Register("%hlasm_machine_gprs")
_CC = Register("%hlasm_machine_cc")
_PROGRAM_MASK = Register("%hlasm_machine_pm")
_TOD_LAST = Register("%hlasm_machine_tod_last")
_ARS_SIZE = Register("%hlasm_machine_ars_size")
_ARS = Register("%hlasm_machine_ars")


def machine_allocation() -> tuple[InstructionBase, ...]:
    return (
        Const.int_(_GPRS_SIZE, GPR_COUNT * GPR_BYTES),
        AllocRegion(result_reg=_GPRS, size_reg=_GPRS_SIZE),
        StoreVar(name=GPRS_VAR, value_reg=_GPRS),
        Const.int_(_CC, INITIAL_CC),
        StoreVar(name=CC_VAR, value_reg=_CC),
        Const.int_(_PROGRAM_MASK, INITIAL_PROGRAM_MASK),
        StoreVar(name=PROGRAM_MASK_VAR, value_reg=_PROGRAM_MASK),
        Const.int_(_TOD_LAST, 0),
        StoreVar(name=TOD_LAST_VAR, value_reg=_TOD_LAST),
    )


def access_register_allocation() -> tuple[InstructionBase, ...]:
    return (
        Const.int_(_ARS_SIZE, GPR_COUNT * ACCESS_REGISTER_BYTES),
        AllocRegion(result_reg=_ARS, size_reg=_ARS_SIZE),
        StoreVar(name=ACCESS_REGISTERS_VAR, value_reg=_ARS),
    )
