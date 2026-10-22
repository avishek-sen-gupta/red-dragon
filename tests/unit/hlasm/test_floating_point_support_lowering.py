# pyright: standard
"""Floating-point-support lowerings: FPRs in their own region with short forms on the high word, invalid pairs abending before any access, every FPC check before the FPC store, and the simulated-IEEE trap after it."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
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
    reg_operand,
    storage_operand,
)

REGIONS = {"__hlasm_gprs": "gpr", "__hlasm_fprs": "fpr"}
STORAGE = "storage"
FPC = "__hlasm_fpc"
BASE = 12
D8 = storage_operand(8)
ADDRESS = f"read gpr {8 * BASE + 4}+4"
SPECIFICATION = "StoreVar __hlasm_abend S0C6"
DATA = "StoreVar __hlasm_abend S0C7"
READ_FPC = f"LoadVar {FPC}"
WRITE_FPC = f"StoreVar {FPC} reg"

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
    if str(i.name) == FPC:
        return f"LoadVar {i.name}"
    return ""


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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fpr_forms_move_through_the_fpr_region_and_short_forms_touch_the_high_word():
    traces = {
        "LER": _trace("LER", _registers(1, 2)),
        "LDR": _trace("LDR", _registers(1, 2)),
        "LE": _trace("LE", (reg_operand(1), D8)),
        "LDY": _trace("LDY", (reg_operand(1), D8)),
        "STEY": _trace("STEY", (reg_operand(3), D8)),
        "STD": _trace("STD", (reg_operand(3), D8)),
        "LDGR": _trace("LDGR", _registers(1, 2)),
        "LGDR": _trace("LGDR", _registers(2, 1)),
        "LXR": _trace("LXR", _registers(1, 4)),
        "LZER": _trace("LZER", _registers(4)),
        "LZDR": _trace("LZDR", _registers(4)),
        "LZXR": _trace("LZXR", _registers(5)),
        "LCDFR": _trace("LCDFR", _registers(1, 2)),
        "LNDFR": _trace("LNDFR", _registers(1, 2)),
        "LPDFR": _trace("LPDFR", _registers(1, 2)),
        "CPSDR": _trace("CPSDR", _registers(1, 2, 3)),
    }
    sign = ["read fpr 16+8", "write fpr 8+8"]

    assert traces == {
        "LER": ["read fpr 16+4", "write fpr 8+4"],
        "LDR": ["read fpr 16+8", "write fpr 8+8"],
        "LE": [ADDRESS, "read storage +4", "write fpr 8+4"],
        "LDY": [ADDRESS, "read storage +8", "write fpr 8+8"],
        "STEY": ["read fpr 24+4", ADDRESS, "write storage +4"],
        "STD": ["read fpr 24+8", ADDRESS, "write storage +8"],
        "LDGR": ["read gpr 16+8", "write fpr 8+8"],
        "LGDR": ["read fpr 8+8", "write gpr 16+8"],
        "LXR": ["read fpr 32+8", "write fpr 8+8", "read fpr 48+8", "write fpr 24+8"],
        "LZER": ["write fpr 32+4"],
        "LZDR": ["write fpr 32+8"],
        "LZXR": ["write fpr 40+8", "write fpr 56+8"],
        "LCDFR": sign,
        "LNDFR": sign,
        "LPDFR": sign,
        "CPSDR": ["read fpr 24+8", "read fpr 16+8", "write fpr 8+8"],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_register_pairs_abend_before_any_access():
    traces = [
        _trace("LXR", _registers(2, 0)),
        _trace("LXR", _registers(0, 3)),
        _trace("LZXR", _registers(6)),
    ]

    assert traces == [[SPECIFICATION], [SPECIFICATION], [SPECIFICATION]]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fpc_forms_check_before_the_store_and_signal_forms_trap_after_it():
    traces = {
        "EFPC": _trace("EFPC", _registers(2)),
        "STFPC": _trace("STFPC", (D8,)),
        "SFPC": _trace("SFPC", _registers(2)),
        "LFPC": _trace("LFPC", (D8,)),
        "SRNM": _trace("SRNM", (D8,)),
        "SRNMT": _trace("SRNMT", (D8,)),
        "SRNMB": _trace("SRNMB", (D8,)),
        "SFASR": _trace("SFASR", _registers(2)),
        "LFAS": _trace("LFAS", (D8,)),
    }
    signal = [READ_FPC, SPECIFICATION, WRITE_FPC, WRITE_FPC, DATA]

    assert traces == {
        "EFPC": [READ_FPC, "write gpr 20+4"],
        "STFPC": [READ_FPC, ADDRESS, "write storage +4"],
        "SFPC": ["read gpr 20+4", SPECIFICATION, WRITE_FPC],
        "LFPC": [ADDRESS, "read storage +4", SPECIFICATION, WRITE_FPC],
        "SRNM": [ADDRESS, READ_FPC, WRITE_FPC],
        "SRNMT": [ADDRESS, READ_FPC, WRITE_FPC],
        "SRNMB": [ADDRESS, SPECIFICATION, READ_FPC, WRITE_FPC],
        "SFASR": ["read gpr 20+4", *signal],
        "LFAS": [ADDRESS, "read storage +4", *signal],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_form_lowers_without_symbolic():
    statements: Mapping[str, tuple[Operand, ...]] = {
        **{m: _registers(1, 2) for m in ("LER", "LDR", "LXR", "LDGR", "LGDR")},
        **{m: _registers(1, 2) for m in ("LCDFR", "LNDFR", "LPDFR")},
        **{m: (reg_operand(1), D8) for m in ("LE", "LEY", "LD", "LDY")},
        **{m: (reg_operand(1), D8) for m in ("STE", "STEY", "STD", "STDY")},
        **{m: _registers(1) for m in ("LZER", "LZDR", "LZXR", "EFPC")},
        **{m: _registers(1) for m in ("SFPC", "SFASR")},
        **{m: (D8,) for m in ("LFPC", "LFAS", "STFPC", "SRNM", "SRNMB", "SRNMT")},
        "CPSDR": _registers(1, 2, 3),
    }
    lowered = {m: _lowered(m, operands) for m, operands in statements.items()}

    assert len(lowered) == 29
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
