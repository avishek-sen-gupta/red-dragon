# pyright: standard
"""EX and EXRL lowerings: the target resolved at compile time, byte 1 decoded per format, one inline copy per reachable byte under a decision tree where byte 1 selects registers, one lowering with byte 1 in a register where it is a data field, and the abends that stop before any copy."""

import logging
from collections.abc import Sequence

import pytest

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.byte_one_layouts import byte_one_layout
from interpreter.hlasm.execute import lower_execute
from interpreter.hlasm.hlasm_constants import ABEND_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine_statements import MachineStatements
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Const,
    InstructionBase,
    LoadRegion,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    mask_operand,
    reg_operand,
)

SECTION = "T"
EX_OFFSET = 2
TARGET_OFFSET = 40


def _statement(
    mnemonic: str,
    format: str,
    operands: Sequence[Operand],
    offset: int = TARGET_OFFSET,
    length: int = 4,
) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section=SECTION,
        offset=offset,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=mnemonic,
        format=format,
        length=length,
        operands=tuple(operands),
        origin=OpenCodeOrigin(kind="OPEN_CODE", file="t.asm", line=1),
    )


def _storage(displacement: int, index: int = 0) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=index,
        base=12,
        written=AbsAddress(kind="ABS", value=displacement),
    )


def _with_length(length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=0, length=length, base=3
    )


def _at(offset: int, index: int = 0) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=offset,
        index=index,
        base=12,
        written=RelocAddress(kind="RELOC", section=SECTION, offset=offset),
    )


def _ex(r1: int, operand: Operand, mnemonic: str = "EX") -> MachineStatement:
    return _statement(
        mnemonic,
        "RX-a" if mnemonic == "EX" else "RIL-b",
        (reg_operand(r1), operand),
        EX_OFFSET,
        4 if mnemonic == "EX" else 6,
    )


VARIANT_VAR = VarName("__test_variant")
MVC = _statement("MVC", "SS-a", (_with_length(0), _storage(0)), length=6)
CLI = _statement("CLI", "SI", (_storage(4), imm_operand(0x40)))
LHI = _statement("LHI", "RI-a", (reg_operand(3), imm_operand(5)))
AR = _statement("AR", "RR", (reg_operand(2), reg_operand(3)), length=2)


def _marker(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    image = emitter.str_(statement.model_dump_json())
    emitter.emit_inst(StoreVar(name=VARIANT_VAR, value_reg=image))


def _executed(
    ex: MachineStatement, targets: Sequence[MachineStatement]
) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    lower_execute(emitter, ex, MachineStatements((ex, *targets)), _marker)
    return emitter.instructions()


def _stored(ir: Sequence[InstructionBase], name: VarName) -> list[str]:
    consts = _constants(ir)
    return [
        str(consts[str(i.value_reg)])
        for i in ir
        if isinstance(i, StoreVar) and i.name == name
    ]


def _variants(ir: Sequence[InstructionBase]) -> list[MachineStatement]:
    return [
        MachineStatement.model_validate_json(image)
        for image in _stored(ir, VARIANT_VAR)
    ]


def _abends(ir: Sequence[InstructionBase]) -> list[str]:
    return _stored(ir, ABEND_VAR)


def _constants(ir: Sequence[InstructionBase]) -> dict[str, int | str]:
    return {str(i.result_reg): i.value for i in ir if isinstance(i, Const)}


def _compared(ir: Sequence[InstructionBase]) -> list[int]:
    consts = _constants(ir)
    return [
        int(consts[str(i.right)])
        for i in ir
        if isinstance(i, Binop) and i.operator.value == "<"
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_byte_one_layouts_decode_each_formats_fields():
    pack = _statement("PACK", "SS-b", (_with_length(3), _with_length(1)), length=6)
    sll = _statement("SLL", "RS-a", (reg_operand(4), _storage(3)))
    cij = _statement(
        "CIJ",
        "RIE-c",
        (
            reg_operand(1),
            imm_operand(-2),
            mask_operand(8),
            RelocImmOperand(kind="RELOC_IMM", section=SECTION, offset=0),
        ),
        length=6,
    )
    lgr = _statement("LGR", "RRE", (reg_operand(1), reg_operand(2)))
    svc = _statement("SVC", "I", (imm_operand(13),), length=2)
    load = _statement("L", "RX-a", (reg_operand(1), _storage(8, 5)))
    ts = _statement("TS", "SI", (_storage(4),))
    cases = {
        "MVC": (MVC, 0x2C),
        "PACK": (pack, 0x75),
        "SLL": (sll, 0x9F),
        "CIJ": (cij, 0x34),
        "LGR": (lgr, 0x77),
        "SVC": (svc, 0x23),
        "L": (load, 0x9A),
        "CLI": (CLI, 0xC3),
        "LHI": (LHI, 0x7F),
        "AR": (AR, 0x9E),
        "TS": (ts, 0xFF),
    }

    decoded = {
        name: (
            byte_one_layout(target).byte_of(target),
            byte_one_layout(target).field_bits,
            byte_one_layout(target).opcode_bits,
            byte_one_layout(target).variant(target, v).operands,
        )
        for name, (target, v) in cases.items()
    }

    assert decoded == {
        "MVC": (0x00, 0xFF, 0x00, (_with_length(0x2D), _storage(0))),
        "PACK": (0x20, 0xFF, 0x00, (_with_length(8), _with_length(6))),
        "SLL": (0x40, 0xF0, 0x00, (reg_operand(9), _storage(3))),
        "CIJ": (
            0x18,
            0xFF,
            0x00,
            (reg_operand(3), imm_operand(-2), mask_operand(4), cij.operands[3]),
        ),
        "LGR": (0x00, 0x00, 0xFF, lgr.operands),
        "SVC": (0x0D, 0xFF, 0x00, (imm_operand(0x23),)),
        "L": (0x15, 0xFF, 0x00, (reg_operand(9), _storage(8, 10))),
        "CLI": (0x40, 0xFF, 0x00, (_storage(4), imm_operand(0xC3))),
        "LHI": (0x30, 0xF0, 0x0F, (reg_operand(7), imm_operand(5))),
        "AR": (0x23, 0xFF, 0x00, (reg_operand(9), reg_operand(14))),
        "TS": (0x00, 0x00, 0x00, ts.operands),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_r1_zero_or_an_unlowered_target_lowers_one_copy_at_the_execute():
    ex = _ex(0, _at(TARGET_OFFSET))
    exrl = _ex(
        0,
        RelocImmOperand(kind="RELOC_IMM", section=SECTION, offset=TARGET_OFFSET),
        "EXRL",
    )
    unlowered_target = _statement("PR", "E", (), length=2)
    emitter = HlasmEmitter()
    lower_execute(emitter, ex, MachineStatements((ex, AR)), OPCODE_LOWERINGS["AR"])
    direct = HlasmEmitter()
    OPCODE_LOWERINGS["AR"](
        direct, AR.model_copy(update={"offset": EX_OFFSET, "length": 4})
    )
    unlowered = _executed(_ex(2, _at(TARGET_OFFSET)), (unlowered_target,))

    assert (
        emitter.instructions(),
        _variants(_executed(ex, (MVC,))),
        _variants(_executed(exrl, (AR,))),
        _variants(unlowered),
        any(isinstance(i, LoadRegion) for i in unlowered),
    ) == (
        direct.instructions(),
        [MVC.model_copy(update={"offset": EX_OFFSET, "length": 4})],
        [AR.model_copy(update={"offset": EX_OFFSET, "length": 6})],
        [unlowered_target.model_copy(update={"offset": EX_OFFSET, "length": 4})],
        False,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_r1_register_fields_select_one_inline_copy_per_reachable_value():
    lhi = _executed(_ex(2, _at(TARGET_OFFSET)), (LHI,))
    ar = _executed(_ex(2, _at(TARGET_OFFSET)), (AR,))

    assert (
        [v.operands for v in _variants(lhi)],
        _abends(lhi),
        len(_variants(ar)),
        len(_compared(ar)),
        sum(1 for i in ar if isinstance(i, BranchIf)),
        len({i.label for i in ar if isinstance(i, Branch)}),
        sum(1 for i in ar if isinstance(i, Branch)),
        _compared(ar)[0],
        any(isinstance(i, Symbolic) for i in (*lhi, *ar)),
    ) == (
        [(reg_operand(r), imm_operand(5)) for r in (3, 7, 11, 15)],
        ["S0C1"],
        32,
        31,
        31,
        1,
        32,
        0xA3,
        False,
    )


def _region_widths(ir: Sequence[InstructionBase]) -> list[tuple[str, int]]:
    return [
        (type(i).__name__, i.length)
        for i in ir
        if isinstance(i, (LoadRegion, WriteRegion))
    ]


def _ored_constants(ir: Sequence[InstructionBase]) -> list[int]:
    consts = _constants(ir)
    return [
        int(consts[str(i.right)])
        for i in ir
        if isinstance(i, Binop)
        and i.operator == BinopKind.BIT_OR
        and str(i.right) in consts
    ]


def _constant_tests(ir: Sequence[InstructionBase], operator: BinopKind) -> list[int]:
    consts = _constants(ir)
    return [
        int(consts[str(i.right)])
        for i in ir
        if isinstance(i, Binop) and i.operator == operator and str(i.right) in consts
    ]


GPR_LOAD = ("LoadRegion", 4)
GPR_STORE = ("WriteRegion", 4)
SVC_10_GPR_ACCESSES = (GPR_LOAD, GPR_LOAD, GPR_STORE, GPR_LOAD)
SVC_11_GPR_ACCESSES = (GPR_LOAD, GPR_STORE, GPR_STORE, GPR_STORE)
SVC_120_GPR_ACCESSES = (GPR_LOAD, GPR_LOAD, GPR_STORE, GPR_LOAD, GPR_STORE)
NAME_LOAD = ("LoadRegion", 8)
SVC_6_ACCESSES = (
    GPR_LOAD,
    ("LoadRegion", 4),
    NAME_LOAD,
    GPR_STORE,
    GPR_STORE,
    NAME_LOAD,
    GPR_STORE,
)
SVC_8_ACCESSES = (GPR_LOAD, GPR_LOAD, NAME_LOAD, *(GPR_STORE,) * 5)
SVC_9_ACCESSES = (GPR_LOAD, NAME_LOAD, GPR_STORE, GPR_STORE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_data_field_target_lowers_once_with_byte_one_from_r1():
    svc = _statement("SVC", "I", (imm_operand(0),), length=2)
    lowered = {
        name: _executed(_ex(2, _at(TARGET_OFFSET)), (target,))
        for name, target in {"MVC": MVC, "CLI": CLI, "SVC": svc}.items()
    }

    assert {
        name: (
            _variants(ir),
            _ored_constants(ir),
            _constant_tests(ir, BinopKind.LT),
            _constant_tests(ir, BinopKind.EQ),
            _region_widths(ir),
            any(isinstance(i, Symbolic) for i in ir),
        )
        for name, ir in lowered.items()
    } == {
        "MVC": (
            [],
            [0x00],
            [],
            [],
            [
                ("LoadRegion", 4),
                ("LoadRegion", 4),
                ("LoadRegion", 4),
                ("LoadRegion", 1),
                ("WriteRegion", 1),
                *(
                    access
                    for size in (256, 128, 64, 32, 16, 8, 4, 2, 1)
                    for access in (("LoadRegion", size), ("WriteRegion", size))
                ),
            ],
            False,
        ),
        "CLI": (
            [],
            [0x40],
            [],
            [],
            [("LoadRegion", 4), ("LoadRegion", 4), ("LoadRegion", 1)],
            False,
        ),
        "SVC": (
            [],
            [0x00, 0xF, 0x80000000],
            [],
            [35, 13, 10, 0, 11, 1, 120, 6, 8, 9],
            [
                ("LoadRegion", 4),
                ("LoadRegion", 4),
                ("LoadRegion", 2),
                ("LoadRegion", 1),
                ("LoadRegion", 4),
                *SVC_10_GPR_ACCESSES,
                *SVC_11_GPR_ACCESSES,
                *SVC_120_GPR_ACCESSES,
                *SVC_6_ACCESSES,
                *SVC_8_ACCESSES,
                *SVC_9_ACCESSES,
            ],
            False,
        ),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_execute_and_specification_exceptions_abend_before_any_copy():
    inner = _ex(0, _at(0))
    inner_rl = _statement(
        "EXRL",
        "RIL-b",
        (reg_operand(0), RelocImmOperand(kind="RELOC_IMM", section=SECTION, offset=0)),
    )
    tbegin = _statement("TBEGIN", "SIL", (_storage(0), imm_operand(0)), length=6)
    abends = {
        name: _executed(_ex(2, _at(at)), targets)
        for name, (at, targets) in {
            "EX": (
                TARGET_OFFSET,
                (inner.model_copy(update={"offset": TARGET_OFFSET}),),
            ),
            "EXRL": (TARGET_OFFSET, (inner_rl,)),
            "TBEGIN": (TARGET_OFFSET, (tbegin,)),
            "odd": (TARGET_OFFSET + 1, (MVC,)),
        }.items()
    }

    assert {
        name: (_abends(ir), _variants(ir), any(isinstance(i, LoadRegion) for i in ir))
        for name, ir in abends.items()
    } == {
        "EX": (["S0C3"], [], False),
        "EXRL": (["S0C3"], [], False),
        "TBEGIN": (["S0C3"], [], False),
        "odd": (["S0C6"], [], False),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unresolved_targets_abend_with_a_warning(caplog: pytest.LogCaptureFixture):
    unresolved = {
        "explicit base": _ex(2, _storage(TARGET_OFFSET)),
        "indexed": _ex(2, _at(TARGET_OFFSET, 4)),
        "no statement": _ex(2, _at(TARGET_OFFSET + 8)),
        "absolute EXRL": _ex(2, imm_operand(TARGET_OFFSET), "EXRL"),
    }
    with caplog.at_level(logging.WARNING, logger="interpreter.hlasm.execute"):
        lowered = {name: _executed(ex, (MVC,)) for name, ex in unresolved.items()}

    assert (
        {name: (_abends(ir), _variants(ir)) for name, ir in lowered.items()},
        [r.getMessage() for r in caplog.records],
    ) == (
        {name: (["S0C1"], []) for name in unresolved},
        [
            "EX in T at offset 2 (t.asm:1): target not written as a relocatable address; it abends S0C1",
            "EX in T at offset 2 (t.asm:1): target indexed by R4; it abends S0C1",
            "EX in T at offset 2 (t.asm:1): no machine statement at T+48; it abends S0C1",
            "EXRL in T at offset 2 (t.asm:1): target not written as a relocatable address; it abends S0C1",
        ],
    )
