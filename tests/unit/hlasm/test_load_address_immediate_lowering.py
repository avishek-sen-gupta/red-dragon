# pyright: standard
"""Load address and immediate lowerings: which GPR bytes they read and write, the index scaling, and no CC."""

from collections.abc import Sequence

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    BranchIf,
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from tests.covers import NotLanguageFeature, covers

INDEX = 3
BASE = 4
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
        length=6,
        operands=tuple(operands),
        origin=OpenCodeOrigin(kind="OPEN_CODE", file="t.asm", line=1),
    )


def _reg(value: int) -> RegOperand:
    return RegOperand(kind="REG", value=value)


def _imm(value: int) -> ImmOperand:
    return ImmOperand(kind="IMM", value=value)


def _indexed(displacement: int) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE", displacement=displacement, index=INDEX, base=BASE
    )


def _lowered(statement: MachineStatement) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[statement.base_mnemonic](emitter, statement)
    return emitter.instructions()


def _gpr_accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, int, int | str]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    gprs = frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    return [
        (type(i).__name__, i.length, consts.get(i.offset_reg, "computed"))
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion) and i.region_reg in gprs
    ]


def _shifts(ir: Sequence[InstructionBase]) -> list[int | str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        consts.get(i.right, "computed")
        for i in ir
        if isinstance(i, Binop) and i.operator == BinopKind.LSHIFT
    ]


def _untouched_control(ir: Sequence[InstructionBase]) -> list[InstructionBase]:
    return [i for i in ir if isinstance(i, BranchIf | StoreVar | Symbolic)]


def _low(r: int) -> tuple[int, int]:
    return 4, 8 * r + 4


def _full(r: int) -> tuple[int, int]:
    return 8, 8 * r


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_address_reads_index_and_base_and_writes_only_the_low_word():
    ir = _lowered(_statement("LAY", (_reg(2), _indexed(-3))))

    assert _gpr_accesses(ir) == [
        ("LoadRegion", *_low(INDEX)),
        ("LoadRegion", *_low(BASE)),
        ("WriteRegion", *_low(2)),
    ]
    assert _shifts(ir) == []
    assert _untouched_control(ir) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_indexed_address_shifts_the_index_sum_before_adding_the_base():
    ir = _lowered(_statement("LXAG", (MaskOperand(kind="MASK", value=2), _indexed(1))))

    assert _gpr_accesses(ir) == [
        ("LoadRegion", *_low(INDEX)),
        ("LoadRegion", *_low(BASE)),
        ("WriteRegion", *_low(2)),
    ]
    assert _shifts(ir) == [3]
    binops = [i for i in ir if isinstance(i, Binop)]
    assert [b.operator for b in binops] == [
        BinopKind.ADD,
        BinopKind.LSHIFT,
        BinopKind.ADD,
        BinopKind.BIT_AND,
        BinopKind.MOD,
    ]
    assert [b.left for b in binops[1:4]] == [b.result_reg for b in binops[0:3]]
    assert _untouched_control(ir) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_immediates_write_the_register_width_and_inserts_read_it_first():
    loaded = _lowered(_statement("LLIHF", (_reg(2), _imm(-1))))
    halfword = _lowered(_statement("LHI", (_reg(2), _imm(-1))))
    inserted = _lowered(_statement("IIHL", (_reg(2), _imm(0x8002))))

    assert _gpr_accesses(loaded) == [("WriteRegion", *_full(2))]
    assert _gpr_accesses(halfword) == [("WriteRegion", *_low(2))]
    assert _gpr_accesses(inserted) == [
        ("LoadRegion", *_full(2)),
        ("WriteRegion", *_full(2)),
    ]
    assert [_untouched_control(ir) for ir in (loaded, halfword, inserted)] == [
        [],
        [],
        [],
    ]
