# pyright: standard
"""High-word lowerings: the register halves each form reads, R1's high word as the only register written, which forms set the CC or check overflow, BRCTH's target before its count, and LFHAT's trap after its load."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Const,
    Halt_,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    describe,
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)

GPRS = "__hlasm_gprs"
WORD = 1 << 32
BASE = 12
HIGH = 0
LOW = 4
CC = "StoreVar __hlasm_cc reg"


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _accesses(ir: Sequence[InstructionBase]) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    gprs = frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    return [
        f"{'read' if isinstance(i, LoadRegion) else 'write'} "
        + (
            f"gpr {consts[i.offset_reg]}+{i.length}"
            if i.region_reg in gprs
            else f"storage +{i.length}"
        )
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion)
    ]


def _effects(ir: Sequence[InstructionBase]) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        "write" if isinstance(i, WriteRegion) else describe(i, consts)
        for i in ir
        if isinstance(i, WriteRegion | StoreVar)
    ]


def _gpr(r: int, half: int, width: int = 4) -> str:
    return f"gpr {8 * r + half}+{width}"


def _read(r: int, half: int, width: int = 4) -> str:
    return f"read {_gpr(r, half, width)}"


def _write(r: int, half: int, width: int = 4) -> str:
    return f"write {_gpr(r, half, width)}"


STORAGE_ADDRESS = _read(BASE, LOW)
THREE_REGISTERS = (reg_operand(2), reg_operand(3), reg_operand(4))
R2_D8 = (reg_operand(2), storage_operand(8))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_its_named_halves_and_writes_only_r1_high_word():
    lowered = {
        "AHHHR": _lowered("AHHHR", THREE_REGISTERS),
        "AHHLR": _lowered("AHHLR", THREE_REGISTERS),
        "SHHLR": _lowered("SHHLR", THREE_REGISTERS),
        "ALHHHR": _lowered("ALHHHR", THREE_REGISTERS),
        "SLHHLR": _lowered("SLHHLR", THREE_REGISTERS),
        "AIH": _lowered("AIH", (reg_operand(2), imm_operand(-1))),
        "ALSIH": _lowered("ALSIH", (reg_operand(2), imm_operand(-1))),
        "ALSIHN": _lowered("ALSIHN", (reg_operand(2), imm_operand(-1))),
        "CHHR": _lowered("CHHR", (reg_operand(2), reg_operand(3))),
        "CLHLR": _lowered("CLHLR", (reg_operand(2), reg_operand(3))),
        "CHF": _lowered("CHF", R2_D8),
        "CLIH": _lowered("CLIH", (reg_operand(2), imm_operand(7))),
        "LBH": _lowered("LBH", R2_D8),
        "LLHH": _lowered("LLHH", R2_D8),
        "LFH": _lowered("LFH", R2_D8),
        "STCH": _lowered("STCH", R2_D8),
        "STFH": _lowered("STFH", R2_D8),
        "LMH": _lowered("LMH", (reg_operand(15), reg_operand(0), storage_operand(8))),
        "STMH": _lowered("STMH", (reg_operand(2), reg_operand(3), storage_operand(8))),
        "ICMH": _lowered(
            "ICMH", (reg_operand(2), mask_operand(0b1010), storage_operand(8))
        ),
        "STCMH": _lowered(
            "STCMH", (reg_operand(2), mask_operand(0b0111), storage_operand(8))
        ),
        "CLMH": _lowered(
            "CLMH", (reg_operand(2), mask_operand(0b1000), storage_operand(8))
        ),
    }
    hh = [_read(3, HIGH), _read(4, HIGH), _write(2, HIGH)]
    hl = [_read(3, HIGH), _read(4, LOW), _write(2, HIGH)]
    immediate = [_read(2, HIGH), _write(2, HIGH)]

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "AHHHR": hh,
        "AHHLR": hl,
        "SHHLR": hl,
        "ALHHHR": hh,
        "SLHHLR": hl,
        "AIH": immediate,
        "ALSIH": immediate,
        "ALSIHN": immediate,
        "CHHR": [_read(2, HIGH), _read(3, HIGH)],
        "CLHLR": [_read(2, HIGH), _read(3, LOW)],
        "CHF": [_read(2, HIGH), STORAGE_ADDRESS, "read storage +4"],
        "CLIH": [_read(2, HIGH)],
        "LBH": [STORAGE_ADDRESS, "read storage +1", _write(2, HIGH)],
        "LLHH": [STORAGE_ADDRESS, "read storage +2", _write(2, HIGH)],
        "LFH": [STORAGE_ADDRESS, "read storage +4", _write(2, HIGH)],
        "STCH": [_read(2, HIGH), STORAGE_ADDRESS, "write storage +1"],
        "STFH": [_read(2, HIGH), STORAGE_ADDRESS, "write storage +4"],
        "LMH": [
            STORAGE_ADDRESS,
            "read storage +4",
            _write(15, HIGH),
            "read storage +4",
            _write(0, HIGH),
        ],
        "STMH": [
            STORAGE_ADDRESS,
            _read(2, HIGH),
            "write storage +4",
            _read(3, HIGH),
            "write storage +4",
        ],
        "ICMH": [STORAGE_ADDRESS, "read storage +2", _read(2, HIGH), _write(2, HIGH)],
        "STCMH": [STORAGE_ADDRESS, _read(2, HIGH), "write storage +3"],
        "CLMH": [_read(2, HIGH), STORAGE_ADDRESS, "read storage +1"],
    }
    signed = ["write", CC, "StoreVar __hlasm_abend S0C8"]
    assert {m: _effects(ir) for m, ir in lowered.items()} == {
        "AHHHR": signed,
        "AHHLR": signed,
        "SHHLR": signed,
        "ALHHHR": ["write", CC],
        "SLHHLR": ["write", CC],
        "AIH": signed,
        "ALSIH": ["write", CC],
        "ALSIHN": ["write"],
        "CHHR": [CC],
        "CLHLR": [CC],
        "CHF": [CC],
        "CLIH": [CC],
        "LBH": ["write"],
        "LLHH": ["write"],
        "LFH": ["write"],
        "STCH": ["write"],
        "STFH": ["write"],
        "LMH": ["write", "write"],
        "STMH": ["write", "write"],
        "ICMH": ["write", CC],
        "STCMH": ["write"],
        "CLMH": [CC],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


def _shape(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    ir = _lowered(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        describe(i, consts)
        for i in ir
        if isinstance(
            i,
            (
                LoadVar,
                StoreVar,
                BranchIf,
                Branch,
                LoadRegion,
                WriteRegion,
                Binop,
                Halt_,
            ),
        )
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_brcth_takes_the_target_then_counts_down_the_high_word_and_lfhat_traps_after_loading():
    relative = RelocImmOperand(kind="RELOC_IMM", section="T", offset=40)

    assert _shape("BRCTH", (reg_operand(4), relative)) == [
        "LoadVar __hlasm_sect_T",
        "+ 40",
        "LoadVar __hlasm_gprs",
        "LoadRegion 32+4",
        "- 1",
        f"% {WORD}",
        "LoadVar __hlasm_gprs",
        f"% {WORD}",
        "WriteRegion 32+4",
        "!= 0",
        "BranchIf",
        "StoreVar __hlasm_target reg",
        "Branch hl_dispatch",
    ]
    assert _shape("LFHAT", R2_D8) == [
        "LoadVar __hlasm_gprs",
        "LoadRegion 100+4",
        "+ reg",
        "& 2147483647",
        "LoadRegion 0+4",
        "LoadVar __hlasm_gprs",
        f"% {WORD}",
        "WriteRegion 16+4",
        "== 0",
        "BranchIf",
        "StoreVar __hlasm_abend S0C7",
        "Halt_",
    ]
