# pyright: standard
"""Conditional load and store, select and bit-count lowerings: the CC mask tested before any operand is touched, SELECT's reads before its write, FLOGR's odd-pair abend, branch-free counts, and one loop for BEXTG and BDEPG."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.operand import Operand
from interpreter.func_name import FuncName
from interpreter.hlasm.bit_counts import (
    EVERY_BYTE,
    any_one,
    leading_zeros,
    leftmost_one,
    population,
    population_by_byte,
    smeared_right,
    trailing_zeros,
)
from interpreter.hlasm.hlasm_constants import (
    BINARY_BYTES_TO_INT,
    CC_VAR,
    INT_TO_BINARY_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    Halt_,
    InstructionBase,
    Label_,
    LoadRegion,
    LoadVar,
    Return_,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    describe,
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)
from tests.unit.hlasm.straight_line_vm import returned_value

BASE = 12
SRC = 0x01234567_89ABCDEF
ONES = 0xFFFFFFFF_FFFFFFFF
BIT_0 = 1 << 63
CONVERSIONS = frozenset({BINARY_BYTES_TO_INT, INT_TO_BINARY_BYTES})


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _shape(ir: Sequence[InstructionBase]) -> list[str]:
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
                Symbolic,
            ),
        )
    ]


def _gpr(offset: int, width: int) -> list[str]:
    return ["LoadVar __hlasm_gprs", f"LoadRegion {offset}+{width}"]


def _written(offset: int, width: int) -> list[str]:
    return [
        "LoadVar __hlasm_gprs",
        f"% {1 << (8 * width)}",
        f"WriteRegion {offset}+{width}",
    ]


def _when(mask: int) -> list[str]:
    return ["LoadVar __hlasm_cc", ">> reg", f"& {mask}", "!= 0", "BranchIf"]


STORAGE_16 = [*_gpr(8 * BASE + 4, 4), "+ reg", "& 2147483647"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_on_condition_forms_test_the_cc_mask_before_touching_an_operand():
    shapes = {
        name: _shape(_lowered(name, operands))
        for name, operands in {
            "LOCR": (reg_operand(4), reg_operand(5), mask_operand(8)),
            "LOCGR": (reg_operand(4), reg_operand(5), mask_operand(4)),
            "LOCFHR": (reg_operand(4), reg_operand(5), mask_operand(2)),
            "LOC": (reg_operand(4), storage_operand(16), mask_operand(7)),
            "LOCFH": (reg_operand(4), storage_operand(16), mask_operand(1)),
            "LOCHHI": (reg_operand(4), imm_operand(-1), mask_operand(13)),
            "STOCG": (reg_operand(4), storage_operand(16), mask_operand(14)),
            "STOCFH": (reg_operand(4), storage_operand(16), mask_operand(0)),
        }.items()
    }

    assert shapes == {
        "LOCR": [*_when(8), *_gpr(44, 4), *_written(36, 4)],
        "LOCGR": [*_when(4), *_gpr(40, 8), *_written(32, 8)],
        "LOCFHR": [*_when(2), *_gpr(40, 4), *_written(32, 4)],
        "LOC": [*_when(7), *STORAGE_16, "LoadRegion 0+4", *_written(36, 4)],
        "LOCFH": [*_when(1), *STORAGE_16, "LoadRegion 0+4", *_written(32, 4)],
        "LOCHHI": [*_when(13), "+ 32768", "% 65536", "- 32768", *_written(32, 4)],
        "STOCG": [
            *_when(14),
            *_gpr(32, 8),
            *STORAGE_16,
            "% 18446744073709551616",
            "WriteRegion 0+8",
        ],
        "STOCFH": [
            *_when(0),
            *_gpr(32, 4),
            *STORAGE_16,
            "% 4294967296",
            "WriteRegion 0+4",
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_select_reads_both_operands_then_writes_the_third_and_the_second_if_selected():
    shapes = {
        name: _shape(
            _lowered(
                name, (reg_operand(4), reg_operand(5), reg_operand(6), mask_operand(9))
            )
        )
        for name in ("SELR", "SELGR", "SELFHR")
    }

    assert shapes == {
        "SELR": [
            *_gpr(44, 4),
            *_gpr(52, 4),
            *_written(36, 4),
            *_when(9),
            *_written(36, 4),
        ],
        "SELGR": [
            *_gpr(40, 8),
            *_gpr(48, 8),
            *_written(32, 8),
            *_when(9),
            *_written(32, 8),
        ],
        "SELFHR": [
            *_gpr(40, 4),
            *_gpr(48, 4),
            *_written(32, 4),
            *_when(9),
            *_written(32, 4),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_flogr_with_an_odd_first_register_abends_s0c6_before_any_register_is_read():
    shape = _shape(_lowered("FLOGR", (reg_operand(5), reg_operand(2))))

    assert shape == ["StoreVar __hlasm_abend S0C6", "Halt_"]


def _called(ir: Sequence[InstructionBase]) -> frozenset[FuncName]:
    return frozenset(i.func_name for i in ir if isinstance(i, CallFunction))


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        type(i).__name__
        for i in ir
        if isinstance(i, (BranchIf, Branch, Label_, Symbolic))
    ]


def _cc_stores(ir: Sequence[InstructionBase]) -> int:
    return sum(1 for i in ir if isinstance(i, StoreVar) and i.name == CC_VAR)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_counts_lower_branch_free_with_no_builtin_and_only_flogr_and_popcnt_set_the_cc():
    lowered = {
        "FLOGR": _lowered("FLOGR", (reg_operand(6), reg_operand(5))),
        "POPCNT": _lowered("POPCNT", (reg_operand(4), reg_operand(5))),
        "POPCNT 8": _lowered(
            "POPCNT", (reg_operand(4), reg_operand(5), mask_operand(8))
        ),
        "CLZG": _lowered("CLZG", (reg_operand(4), reg_operand(5))),
        "CTZG": _lowered("CTZG", (reg_operand(4), reg_operand(5))),
    }

    assert {name: _control(ir) for name, ir in lowered.items()} == {
        name: [] for name in lowered
    }
    assert {name: _called(ir) for name, ir in lowered.items()} == {
        name: CONVERSIONS for name in lowered
    }
    assert {name: _cc_stores(ir) for name, ir in lowered.items()} == {
        "FLOGR": 1,
        "POPCNT": 1,
        "POPCNT 8": 1,
        "CLZG": 0,
        "CTZG": 0,
    }
    assert {name: _shape(ir)[-3:] for name, ir in lowered.items()} == {
        "FLOGR": ["& 1", "<< 1", "StoreVar __hlasm_cc reg"],
        "POPCNT": [">> 64", "& 1", "StoreVar __hlasm_cc reg"],
        "POPCNT 8": [">> 64", "& 1", "StoreVar __hlasm_cc reg"],
        "CLZG": _written(32, 8),
        "CTZG": _written(32, 8),
    }
    assert {
        name: _shape(lowered[name]).count(f"* {EVERY_BYTE}")
        for name in ("POPCNT", "POPCNT 8")
    } == {"POPCNT": 0, "POPCNT 8": 1}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bit_extract_and_deposit_run_one_loop_over_the_mask_with_no_builtin():
    lowered = {
        name: _lowered(name, (reg_operand(4), reg_operand(5), reg_operand(6)))
        for name in ("BEXTG", "BDEPG")
    }

    assert {name: _control(ir) for name, ir in lowered.items()} == {
        name: ["Label_", "BranchIf", "Label_", "Branch", "Label_"] for name in lowered
    }
    assert {name: _called(ir) for name, ir in lowered.items()} == {
        "BEXTG": CONVERSIONS,
        "BDEPG": CONVERSIONS,
    }
    assert {name: _shape(ir)[:4] for name, ir in lowered.items()} == {
        name: [*_gpr(40, 8), *_gpr(48, 8)] for name in lowered
    }
    assert {name: _shape(ir)[-4:] for name, ir in lowered.items()} == {
        name: ["LoadVar __hlasm_bits_result", *_written(32, 8)] for name in lowered
    }


type Count = Callable[[HlasmEmitter, Register], Register]

VALUE = Register("%value")


def _computed(count: Count, value: int) -> int | list[int]:
    emitter = HlasmEmitter()
    result = count(emitter, VALUE)
    emitter.emit_inst(Return_(value_reg=result))
    return returned_value(emitter.instructions(), {"%value": value})


COUNTS: Mapping[str, Count] = {
    "population_by_byte": population_by_byte,
    "population": population,
    "leading_zeros": leading_zeros,
    "trailing_zeros": trailing_zeros,
    "leftmost_one": lambda emitter, value: leftmost_one(
        emitter, smeared_right(emitter, value)
    ),
    "any_one": lambda emitter, value: any_one(emitter, smeared_right(emitter, value)),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bit_count_ir_computes_each_count():
    values = (0, 1, BIT_0, SRC, ONES)

    assert {
        name: [_computed(count, value) for value in values]
        for name, count in COUNTS.items()
    } == {
        "population_by_byte": [
            0,
            1,
            0x01000000_00000000,
            0x01030305_03050507,
            0x08080808_08080808,
        ],
        "population": [0, 1, 1, 32, 64],
        "leading_zeros": [64, 63, 0, 7, 0],
        "trailing_zeros": [64, 0, 63, 0, 0],
        "leftmost_one": [0, 1, BIT_0, 0x01000000_00000000, BIT_0],
        "any_one": [0, 1, 1, 1, 1],
    }
