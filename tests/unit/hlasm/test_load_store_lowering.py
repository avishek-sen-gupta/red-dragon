# pyright: standard
"""Load and store lowerings: which GPR bytes and storage widths each one reads and writes."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
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
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

BASE = 12
GPRS = "__hlasm_gprs"


def _statement(mnemonic: str, operands: Sequence[Operand]) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section="T",
        offset=2,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=mnemonic,
        format="",
        length=4,
        operands=tuple(operands),
        origin=OpenCodeOrigin(kind="OPEN_CODE", file="t.asm", line=1),
    )


def _reg(value: int) -> RegOperand:
    return RegOperand(kind="REG", value=value)


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


def _lowered(statement: MachineStatement) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[statement.base_mnemonic](emitter, statement)
    return emitter.instructions()


def _gpr_regions(ir: Sequence[InstructionBase]) -> frozenset[Register]:
    return frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )


def _accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, str, int, int | str]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    gprs = _gpr_regions(ir)
    return [
        (
            type(i).__name__,
            "gpr" if i.region_reg in gprs else "storage",
            i.length,
            consts.get(i.offset_reg, "computed"),
        )
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion)
    ]


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, BranchIf | Halt_ | StoreVar)
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_reads_the_base_then_a_storage_word_into_the_low_word():
    ir = _lowered(_statement("L", (_reg(2), _storage(8))))

    assert _accesses(ir) == [
        ("LoadRegion", "gpr", 4, 8 * BASE + 4),
        ("LoadRegion", "storage", 4, 0),
        ("WriteRegion", "gpr", 4, 8 * 2 + 4),
    ]
    assert _control(ir) == []
    assert [i for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_relative_long_loads_check_alignment_only_for_words_and_doublewords():
    target = RelocImmOperand(kind="RELOC_IMM", section="T", offset=16)
    ir = _lowered(_statement("LGRL", (_reg(3), target)))
    halfword = _lowered(_statement("LHRL", (_reg(3), target)))

    assert _accesses(ir) == [
        ("LoadRegion", "storage", 8, 0),
        ("WriteRegion", "gpr", 8, 8 * 3),
    ]
    assert _control(ir) == ["BranchIf", "StoreVar:__hlasm_abend", "Halt_"]
    assert _accesses(halfword) == [
        ("LoadRegion", "storage", 2, 0),
        ("WriteRegion", "gpr", 4, 8 * 3 + 4),
    ]
    assert _control(halfword) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_insert_under_mask_reads_its_bytes_merges_the_low_word_and_sets_cc():
    ir = _lowered(
        _statement(
            "ICM", (_reg(2), MaskOperand(kind="MASK", value=0b1010), _storage(8))
        )
    )

    assert _accesses(ir) == [
        ("LoadRegion", "gpr", 4, 8 * BASE + 4),
        ("LoadRegion", "storage", 2, 0),
        ("LoadRegion", "gpr", 4, 8 * 2 + 4),
        ("WriteRegion", "gpr", 4, 8 * 2 + 4),
    ]
    assert _control(ir) == ["StoreVar:__hlasm_cc"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_store_multiple_wraps_and_writes_one_word_per_register():
    ir = _lowered(_statement("STM", (_reg(14), _reg(1), _storage(8))))

    assert _accesses(ir) == [
        ("LoadRegion", "gpr", 4, 8 * BASE + 4),
        *(
            access
            for at, r in enumerate((14, 15, 0, 1))
            for access in (
                ("LoadRegion", "gpr", 4, 8 * r + 4),
                ("WriteRegion", "storage", 4, 4 * at),
            )
        ),
    ]
