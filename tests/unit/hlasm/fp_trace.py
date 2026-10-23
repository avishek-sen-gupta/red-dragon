# pyright: standard
"""Traces of HLASM lowerings as the region accesses, FPC, program-mask and CC accesses, abends, floating-point builtin calls and decimal-lane function calls they emit, for BFP, HFP and DFP lowering tests."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    CallFunction,
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    WriteRegion,
)
from interpreter.register import Register
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    reg_operand,
    storage_operand,
)

REGIONS = {"__hlasm_gprs": "gpr", "__hlasm_fprs": "fpr"}
STORAGE = "storage"
FPC = "__hlasm_fpc"
D8 = storage_operand(8)
ADDRESS = "read gpr 100+4"
SPECIFICATION = "StoreVar __hlasm_abend S0C6"
DATA = "StoreVar __hlasm_abend S0C7"
READ_FPC = f"LoadVar {FPC}"
READ_PM = "LoadVar __hlasm_pm"
WRITE_FPC = f"StoreVar {FPC} reg"
CC = "StoreVar __hlasm_cc reg"
BFP = "__hlasm_bfp_"
HFP = "__hlasm_hfp_"
DFP = "__hlasm_dfp_"
DECIMAL = "__hlasm_decimal_"
PFPO = "__hlasm_pfpo"

type Regions = Mapping[Register, str]
type Consts = Mapping[Register, int | str]


def lowered_ir(
    mnemonic: str, operands: Sequence[Operand]
) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _access(
    verb: str, i: LoadRegion | WriteRegion, regions: Regions, consts: Consts
) -> str:
    region = regions.get(i.region_reg, STORAGE)
    offset = {STORAGE: ""}.get(region, f"{consts.get(i.offset_reg, '')}")
    return f"{verb} {region} {offset}+{i.length}"


@singledispatch
def _shown(i: InstructionBase, regions: Regions, consts: Consts) -> str:
    return ""


@_shown.register
def _shown_read(i: LoadRegion, regions: Regions, consts: Consts) -> str:
    return _access("read", i, regions, consts)


@_shown.register
def _shown_write(i: WriteRegion, regions: Regions, consts: Consts) -> str:
    return _access("write", i, regions, consts)


@_shown.register
def _shown_store(i: StoreVar, regions: Regions, consts: Consts) -> str:
    return f"StoreVar {i.name} {consts.get(i.value_reg, 'reg')}"


@_shown.register
def _shown_load(i: LoadVar, regions: Regions, consts: Consts) -> str:
    return {FPC: READ_FPC, "__hlasm_pm": READ_PM}.get(str(i.name), "")


@_shown.register
def _shown_call(i: CallFunction, regions: Regions, consts: Consts) -> str:
    name = str(i.func_name)
    shown = {
        BFP: "call ",
        HFP: "call hfp ",
        DFP: "call dfp ",
        DECIMAL: "call decimal ",
        PFPO: "call pfpo",
    }
    return next((f"{shown[p]}{name[len(p):]}" for p in shown if name.startswith(p)), "")


def trace(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    ir = lowered_ir(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    regions = {
        i.result_reg: REGIONS[str(i.name)]
        for i in ir
        if isinstance(i, LoadVar) and str(i.name) in REGIONS
    }
    shown = (_shown(i, regions, consts) for i in ir)
    return [entry for entry in shown if entry]


def registers(*values: int) -> tuple[Operand, ...]:
    return tuple(reg_operand(v) for v in values)


def ladder(*deliver: str) -> list[str]:
    return [
        READ_FPC,
        WRITE_FPC,
        DATA,
        *deliver,
        WRITE_FPC,
        DATA,
        WRITE_FPC,
        WRITE_FPC,
        DATA,
    ]
