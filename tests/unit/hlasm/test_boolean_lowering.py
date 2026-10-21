# pyright: standard
"""Boolean lowerings: the operand widths they read and write, the field they replace, the CC, and the storage-to-storage byte loop."""

from collections.abc import Sequence

from hlasm_asg.program.imm_operand import ImmOperand
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
CC = "__hlasm_cc"
AT = "__hlasm_ss_at"


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


def _with_length(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=displacement, length=length, base=BASE
    )


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


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


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, Branch | BranchIf | Halt_ | Label_ | StoreVar)
    ]


def _bounds(ir: Sequence[InstructionBase]) -> list[int | str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        consts.get(i.right, "computed")
        for i in ir
        if isinstance(i, Binop) and i.operator == BinopKind.LT
    ]


def _gpr(r: int, width: int) -> tuple[str, int, int]:
    return "gpr", width, 8 * r + 8 - width


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_and_writes_its_operand_widths_then_sets_cc():
    lowered = {
        "NRK": _lowered(_statement("NRK", (_reg(5), _reg(3), _reg(4)))),
        "NG": _lowered(_statement("NG", (_reg(2), _storage(8)))),
        "NNGRK": _lowered(_statement("NNGRK", (_reg(5), _reg(3), _reg(4)))),
        "XI": _lowered(_statement("XI", (_storage(8), _imm(0x0F)))),
        "NIHH": _lowered(_statement("NIHH", (_reg(2), _imm(0xFEDC)))),
        "XILF": _lowered(_statement("XILF", (_reg(2), _imm(-1)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "NRK": [
            ("LoadRegion", *_gpr(3, 4)),
            ("LoadRegion", *_gpr(4, 4)),
            ("WriteRegion", *_gpr(5, 4)),
        ],
        "NG": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 8, 0),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "NNGRK": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(4, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "XI": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 1, 0),
            ("WriteRegion", "storage", 1, 0),
        ],
        "NIHH": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(2, 8)),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "XILF": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(2, 8)),
            ("WriteRegion", *_gpr(2, 8)),
        ],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        m: [f"StoreVar:{CC}"] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_storage_to_storage_forms_are_one_byte_loop_whatever_the_length():
    short = _lowered(_statement("NC", (_with_length(8, 1), _storage(40))))
    longest = _lowered(_statement("XC", (_with_length(8, 256), _storage(40))))

    assert (len(short), _accesses(longest), _control(longest)) == (
        len(longest),
        [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 1, 0),
            ("LoadRegion", "storage", 1, 0),
            ("WriteRegion", "storage", 1, 0),
        ],
        [
            f"StoreVar:{CC}",
            f"StoreVar:{AT}",
            "Label_",
            "BranchIf",
            "Label_",
            f"StoreVar:{CC}",
            f"StoreVar:{AT}",
            "Branch",
            "Label_",
        ],
    )
    assert (_bounds(short), _bounds(longest)) == ([1], [256])
    assert [i for i in longest if isinstance(i, Symbolic)] == []
