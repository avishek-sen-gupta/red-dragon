# pyright: standard
"""Storage move lowerings: the widths they store, the MVC block move beside its byte loop, the nibble loops, and the long-move register checks."""

from collections.abc import Sequence

from hlasm_asg.program.abs_address import AbsAddress
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
AT = "__hlasm_ss_at"
ABEND = "__hlasm_abend"


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
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=0,
        base=BASE,
        written=AbsAddress(kind="ABS", value=displacement),
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


def _symbolic(lowered: Sequence[Sequence[InstructionBase]]) -> list[InstructionBase]:
    return [i for ir in lowered for i in ir if isinstance(i, Symbolic)]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_immediate_moves_store_their_width_and_leave_the_cc():
    widths = {"MVI": 1, "MVIY": 1, "MVHHI": 2, "MVHI": 4, "MVGHI": 8}
    lowered = {m: _lowered(_statement(m, (_storage(8), _imm(-2)))) for m in widths}

    assert {m: (_accesses(ir), _control(ir)) for m, ir in lowered.items()} == {
        m: (
            [("LoadRegion", "gpr", 4, 8 * BASE + 4), ("WriteRegion", "storage", w, 0)],
            [],
        )
        for m, w in widths.items()
    }
    assert _symbolic(list(lowered.values())) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mvc_is_a_block_move_unless_the_destination_starts_inside_the_source():
    ir = _lowered(_statement("MVC", (_with_length(8, 256), _storage(9))))
    explicit_zero = _lowered(_statement("MVC", (_with_length(8, 0), _storage(9))))

    assert (_accesses(ir), _control(ir), _bounds(ir), _bounds(explicit_zero)) == (
        [
            ("LoadRegion", "gpr", 4, 8 * BASE + 4),
            ("LoadRegion", "gpr", 4, 8 * BASE + 4),
            ("LoadRegion", "storage", 1, "computed"),
            ("WriteRegion", "storage", 1, "computed"),
            ("LoadRegion", "storage", 256, 0),
            ("WriteRegion", "storage", 256, 0),
        ],
        [
            "BranchIf",
            "Label_",
            f"StoreVar:{AT}",
            "Label_",
            "BranchIf",
            "Label_",
            f"StoreVar:{AT}",
            "Branch",
            "Label_",
            "Branch",
            "Label_",
            "Label_",
        ],
        ["computed", "computed", 256],
        ["computed", "computed", 1],
    )
    assert _symbolic([ir]) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_nibble_moves_read_both_bytes_and_write_one_per_iteration():
    lowered = {
        m: _lowered(_statement(m, (_with_length(8, 3), _storage(40))))
        for m in ("MVN", "MVZ")
    }

    assert {m: (_accesses(ir), _bounds(ir)) for m, ir in lowered.items()} == {
        m: (
            [
                ("LoadRegion", "gpr", 4, 8 * BASE + 4),
                ("LoadRegion", "gpr", 4, 8 * BASE + 4),
                ("LoadRegion", "storage", 1, "computed"),
                ("LoadRegion", "storage", 1, "computed"),
                ("WriteRegion", "storage", 1, "computed"),
            ],
            [3],
        )
        for m in lowered
    }
    assert _symbolic(list(lowered.values())) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_long_moves_on_an_odd_register_abend_before_reading_any_register():
    lowered = [
        _lowered(_statement("MVCL", (_reg(3), _reg(4)))),
        _lowered(_statement("MVCL", (_reg(2), _reg(5)))),
        _lowered(_statement("MVCLE", (_reg(2), _reg(5), _storage(0)))),
        _lowered(_statement("MVCLU", (_reg(3), _reg(4), _storage(0)))),
    ]

    assert [(_accesses(ir), _control(ir)) for ir in lowered] == [
        ([], [f"StoreVar:{ABEND}", "Halt_"])
    ] * 4
