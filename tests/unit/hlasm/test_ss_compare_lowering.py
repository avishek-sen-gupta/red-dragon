# pyright: standard
"""Storage compare lowerings: CLC's single block compare, the long compares' unit loops, and the odd-pair checks; none writes storage."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
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
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from tests.covers import NotLanguageFeature, covers

BASE = 12
GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
CC = "__hlasm_cc"
IMAGE_BUILTIN = "__int_to_binary_bytes"
COMPARISONS = frozenset((BinopKind.EQ, BinopKind.NE, BinopKind.LT, BinopKind.GT))


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


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


def _with_length(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=displacement, length=length, base=BASE
    )


def _lowered(statement: MachineStatement) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[statement.base_mnemonic](emitter, statement)
    return emitter.instructions()


def _accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, str, int, int | str]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    gprs = frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
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


def _storage_accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, int]]:
    return [
        (kind, length)
        for kind, region, length, _ in _accesses(ir)
        if region == "storage"
    ]


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, Branch | BranchIf | Halt_ | Label_ | StoreVar)
    ]


def _image_comparisons(ir: Sequence[InstructionBase]) -> list[InstructionBase]:
    images = frozenset(
        [i.result_reg for i in ir if isinstance(i, LoadRegion)]
        + [
            i.result_reg
            for i in ir
            if isinstance(i, CallFunction) and str(i.func_name) == IMAGE_BUILTIN
        ]
    )
    return [
        i
        for i in ir
        if isinstance(i, Binop)
        and i.operator in COMPARISONS
        and (i.left in images or i.right in images)
    ]


def _symbolic(lowered: Sequence[Sequence[InstructionBase]]) -> list[InstructionBase]:
    return [i for ir in lowered for i in ir if isinstance(i, Symbolic)]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clc_compares_both_blocks_once_and_only_sets_the_cc():
    ir = _lowered(_statement("CLC", (_with_length(8, 256), _storage(300))))
    explicit_zero = _lowered(_statement("CLC", (_with_length(8, 0), _storage(300))))

    assert (
        _accesses(ir),
        _storage_accesses(explicit_zero),
        _control(ir),
    ) == (
        [
            ("LoadRegion", "gpr", 4, 8 * BASE + 4),
            ("LoadRegion", "gpr", 4, 8 * BASE + 4),
            ("LoadRegion", "storage", 256, 0),
            ("LoadRegion", "storage", 256, 0),
        ],
        [("LoadRegion", 1), ("LoadRegion", 1)],
        [f"StoreVar:{CC}"],
    )
    assert _symbolic([ir, explicit_zero]) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_long_compares_read_one_unit_of_each_operand_per_iteration_and_compare_ints():
    lowered = {
        "CLCL": _lowered(_statement("CLCL", (_reg(2), _reg(4)))),
        "CLCLE": _lowered(_statement("CLCLE", (_reg(2), _reg(4), _storage(0)))),
        "CLCLU": _lowered(_statement("CLCLU", (_reg(2), _reg(4), _storage(0)))),
        "CUSE": _lowered(_statement("CUSE", (_reg(2), _reg(4)))),
        "CLST": _lowered(_statement("CLST", (_reg(2), _reg(4)))),
    }

    assert {m: _storage_accesses(ir) for m, ir in lowered.items()} == {
        "CLCL": [("LoadRegion", 1)] * 4,
        "CLCLE": [("LoadRegion", 1)] * 4,
        "CLCLU": [("LoadRegion", 2)] * 4,
        "CUSE": [("LoadRegion", 1)] * 4,
        "CLST": [("LoadRegion", 1)] * 2,
    }
    assert {m: _image_comparisons(ir) for m, ir in lowered.items()} == {
        m: [] for m in lowered
    }
    assert _symbolic(list(lowered.values())) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pair_compares_on_an_odd_register_abend_before_reading_any_register():
    lowered = [
        _lowered(_statement("CLCL", (_reg(3), _reg(4)))),
        _lowered(_statement("CLCL", (_reg(2), _reg(5)))),
        _lowered(_statement("CLCLE", (_reg(2), _reg(5), _storage(0)))),
        _lowered(_statement("CLCLU", (_reg(3), _reg(4), _storage(0)))),
        _lowered(_statement("CUSE", (_reg(2), _reg(7)))),
    ]

    assert [(_accesses(ir), _control(ir)) for ir in lowered] == [
        ([], [f"StoreVar:{ABEND}", "Halt_"])
    ] * 5
