# pyright: standard
"""BFP arithmetic lowerings: operands read in builtin-argument order, one builtin call, then the trap ladder (suppress, deliver scaled, deliver and flag, inexact trap); static checks abend before any access; sign forms are IR alone."""

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
    Symbolic,
    WriteRegion,
)
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    mask_operand,
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
WRITE_FPC = f"StoreVar {FPC} reg"
CC = "StoreVar __hlasm_cc reg"
BFP = "__hlasm_bfp_"

type Regions = Mapping[Register, str]
type Consts = Mapping[Register, int | str]


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
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
    return {FPC: READ_FPC}.get(str(i.name), "")


@_shown.register
def _shown_call(i: CallFunction, regions: Regions, consts: Consts) -> str:
    name = str(i.func_name)
    return f"call {name[len(BFP):]}" if name.startswith(BFP) else ""


def _trace(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    ir = _lowered(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    regions = {
        i.result_reg: REGIONS[str(i.name)]
        for i in ir
        if isinstance(i, LoadVar) and str(i.name) in REGIONS
    }
    shown = (_shown(i, regions, consts) for i in ir)
    return [entry for entry in shown if entry]


def _registers(*values: int) -> tuple[Operand, ...]:
    return tuple(reg_operand(v) for v in values)


def _ladder(*deliver: str) -> list[str]:
    return [
        READ_FPC,
        WRITE_FPC,
        DATA,
        *deliver,
        WRITE_FPC,
        DATA,
        *deliver,
        WRITE_FPC,
        WRITE_FPC,
        DATA,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ieee_forms_read_operands_in_argument_order_then_call_then_trap():
    traces = {
        "ADBR": _trace("ADBR", _registers(2, 4)),
        "AEB": _trace("AEB", (reg_operand(1), D8)),
        "AXBR": _trace("AXBR", _registers(0, 4)),
        "MDBR": _trace("MDBR", _registers(1, 2)),
        "MAEBR": _trace("MAEBR", _registers(1, 3, 2)),
        "MADB": _trace("MADB", (reg_operand(1), reg_operand(3), D8)),
        "MXDBR": _trace("MXDBR", _registers(4, 2)),
        "CDBR": _trace("CDBR", _registers(1, 2)),
        "FIEBR": _trace("FIEBR", (reg_operand(1), mask_operand(0), reg_operand(2))),
        "FIDBRA": _trace(
            "FIDBRA",
            (reg_operand(1), mask_operand(5), reg_operand(2), mask_operand(4)),
        ),
        "DIDBR": _trace("DIDBR", (*_registers(1, 3, 2), mask_operand(0))),
        "DIEBR": _trace("DIEBR", (*_registers(1, 3, 2), mask_operand(7))),
        "TCDB": _trace("TCDB", (reg_operand(1), D8)),
    }

    assert traces == {
        "ADBR": [
            READ_FPC,
            "read fpr 16+8",
            "read fpr 32+8",
            "call add_long",
            *_ladder("write fpr 16+8", CC),
        ],
        "AEB": [
            READ_FPC,
            "read fpr 8+4",
            ADDRESS,
            "read storage +4",
            "call add_short",
            *_ladder("write fpr 8+4", CC),
        ],
        "AXBR": [
            READ_FPC,
            "read fpr 0+8",
            "read fpr 16+8",
            "read fpr 32+8",
            "read fpr 48+8",
            "call add_extended",
            *_ladder("write fpr 0+8", "write fpr 16+8", CC),
        ],
        "MDBR": [
            READ_FPC,
            "read fpr 8+8",
            "read fpr 16+8",
            "call multiply_long",
            *_ladder("write fpr 8+8"),
        ],
        "MAEBR": [
            READ_FPC,
            "read fpr 24+4",
            "read fpr 16+4",
            "read fpr 8+4",
            "call multiply_add_short",
            *_ladder("write fpr 8+4"),
        ],
        "MADB": [
            READ_FPC,
            "read fpr 24+8",
            ADDRESS,
            "read storage +8",
            "read fpr 8+8",
            "call multiply_add_long",
            *_ladder("write fpr 8+8"),
        ],
        "MXDBR": [
            "read fpr 32+8",
            "read fpr 16+8",
            "call multiply_lengthened_long",
            *_ladder("write fpr 32+8", "write fpr 48+8"),
        ],
        "CDBR": ["read fpr 8+8", "read fpr 16+8", "call compare_long", *_ladder(CC)],
        "FIEBR": [
            READ_FPC,
            "read fpr 16+4",
            "call round_to_integral_short",
            *_ladder("write fpr 8+4"),
        ],
        "FIDBRA": [
            "read fpr 16+8",
            "call round_to_integral_long",
            *_ladder("write fpr 8+8"),
        ],
        "DIDBR": [
            READ_FPC,
            READ_FPC,
            "read fpr 8+8",
            "read fpr 16+8",
            "call divide_to_integer_long",
            *_ladder("write fpr 8+8", "write fpr 24+8", CC),
        ],
        "DIEBR": [
            READ_FPC,
            "read fpr 8+4",
            "read fpr 16+4",
            "call divide_to_integer_short",
            *_ladder("write fpr 8+4", "write fpr 24+4", CC),
        ],
        "TCDB": ["read fpr 8+8", ADDRESS, "call test_data_class_long", CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_sign_forms_are_ir_and_load_and_test_traps_an_snan():
    traces = {
        "LCDBR": _trace("LCDBR", _registers(1, 2)),
        "LNEBR": _trace("LNEBR", _registers(1, 2)),
        "LPXBR": _trace("LPXBR", _registers(0, 4)),
        "LTDBR": _trace("LTDBR", _registers(1, 2)),
    }

    assert traces == {
        "LCDBR": ["read fpr 16+8", "write fpr 8+8", CC],
        "LNEBR": ["read fpr 16+4", "write fpr 8+4", CC],
        "LPXBR": [
            "read fpr 32+8",
            "read fpr 48+8",
            "write fpr 0+8",
            "write fpr 16+8",
            CC,
        ],
        "LTDBR": ["read fpr 16+8", *_ladder("write fpr 8+8", CC)],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_modifiers_and_registers_abend_before_any_access():
    traces = [
        _trace("AXBR", _registers(2, 4)),
        _trace("SQXBR", _registers(0, 6)),
        _trace("MXDBR", _registers(2, 4)),
        _trace("MXDB", (reg_operand(6), D8)),
        _trace("TCXB", (reg_operand(2), D8)),
        _trace("LTXBR", _registers(7, 0)),
        _trace("FIEBR", (reg_operand(1), mask_operand(2), reg_operand(2))),
        _trace(
            "FIXBRA",
            (reg_operand(1), mask_operand(4), reg_operand(6), mask_operand(0)),
        ),
        _trace(
            "FIDBRA",
            (reg_operand(1), mask_operand(8), reg_operand(2), mask_operand(0)),
        ),
        _trace("DIEBR", (*_registers(1, 3, 2), mask_operand(2))),
        _trace("DIDBR", (*_registers(1, 1, 2), mask_operand(0))),
        _trace("DIEBR", (*_registers(1, 3, 3), mask_operand(0))),
        _trace("DIDBR", (*_registers(2, 3, 2), mask_operand(0))),
    ]

    assert traces == [[SPECIFICATION]] * 13


RR = _registers(0, 4)
RX = (reg_operand(0), D8)
FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "AEBR ADBR AXBR SEBR SDBR SXBR MEEBR MDBR MXBR MDEBR MXDBR DEBR DDBR DXBR": RR,
    "AEB ADB SEB SDB MEEB MDB MDEB MXDB DEB DDB SQEB SQDB TCEB TCDB TCXB": RX,
    "SQEBR SQDBR SQXBR CEBR CDBR CXBR KEBR KDBR KXBR": RR,
    "CEB CDB KEB KDB": RX,
    "LTEBR LTDBR LTXBR LCEBR LCDBR LCXBR LNEBR LNDBR LNXBR LPEBR LPDBR LPXBR": RR,
    "MAEBR MADBR MSEBR MSDBR": _registers(1, 3, 2),
    "MAEB MADB MSEB MSDB": (reg_operand(1), reg_operand(3), D8),
    "FIEBR FIDBR FIXBR": (reg_operand(0), mask_operand(0), reg_operand(4)),
    "FIEBRA FIDBRA FIXBRA": (
        reg_operand(0),
        mask_operand(0),
        reg_operand(4),
        mask_operand(4),
    ),
    "DIEBR DIDBR": (*_registers(1, 3, 2), mask_operand(4)),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: _lowered(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 70
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
