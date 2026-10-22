# pyright: standard
"""EX and EXRL lowerings: the target resolved at compile time, byte 1 decoded per format, one inline copy per reachable byte under a decision tree, and the abends that stop before any copy."""

import logging
from collections.abc import Sequence

import pytest

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.byte_one_layouts import byte_one_layout
from interpreter.hlasm.execute import lower_execute
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
    Symbolic,
)
from tests.covers import NotLanguageFeature, covers

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


def _reg(value: int) -> RegOperand:
    return RegOperand(kind="REG", value=value)


def _mask(value: int) -> MaskOperand:
    return MaskOperand(kind="MASK", value=value)


def _imm(value: int) -> ImmOperand:
    return ImmOperand(kind="IMM", value=value)


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
        (_reg(r1), operand),
        EX_OFFSET,
        4 if mnemonic == "EX" else 6,
    )


MVC = _statement("MVC", "SS-a", (_with_length(0), _storage(0)), length=6)
CLI = _statement("CLI", "SI", (_storage(4), _imm(0x40)))
LHI = _statement("LHI", "RI-a", (_reg(3), _imm(5)))
AR = _statement("AR", "RR", (_reg(2), _reg(3)), length=2)


def _marker(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    rendered = ",".join(
        str(o.model_dump(exclude={"kind", "written"})) for o in statement.operands
    )
    emitter.emit_inst(
        Const.string(
            emitter.fresh_reg(),
            f"{statement.base_mnemonic}@{statement.offset}+{statement.length} {rendered}",
        )
    )


def _executed(
    ex: MachineStatement, targets: Sequence[MachineStatement]
) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    lower_execute(emitter, ex, MachineStatements((ex, *targets)), _marker)
    return emitter.instructions()


def _markers(ir: Sequence[InstructionBase]) -> list[str]:
    return [str(i.value) for i in ir if isinstance(i, Const) and "@" in str(i.value)]


def _abends(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        str(i.value) for i in ir if isinstance(i, Const) and str(i.value)[:2] == "S0"
    ]


def _constants(ir: Sequence[InstructionBase]) -> dict[str, int]:
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
    sll = _statement("SLL", "RS-a", (_reg(4), _storage(3)))
    cij = _statement(
        "CIJ",
        "RIE-c",
        (
            _reg(1),
            _imm(-2),
            _mask(8),
            RelocImmOperand(kind="RELOC_IMM", section=SECTION, offset=0),
        ),
        length=6,
    )
    lgr = _statement("LGR", "RRE", (_reg(1), _reg(2)))
    svc = _statement("SVC", "I", (_imm(13),), length=2)
    load = _statement("L", "RX-a", (_reg(1), _storage(8, 5)))
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
        "SLL": (0x40, 0xF0, 0x00, (_reg(9), _storage(3))),
        "CIJ": (
            0x18,
            0xFF,
            0x00,
            (_reg(3), _imm(-2), _mask(4), cij.operands[3]),
        ),
        "LGR": (0x00, 0x00, 0xFF, lgr.operands),
        "SVC": (0x0D, 0xFF, 0x00, (_imm(0x23),)),
        "L": (0x15, 0xFF, 0x00, (_reg(9), _storage(8, 10))),
        "CLI": (0x40, 0xFF, 0x00, (_storage(4), _imm(0xC3))),
        "LHI": (0x30, 0xF0, 0x0F, (_reg(7), _imm(5))),
        "AR": (0x23, 0xFF, 0x00, (_reg(9), _reg(14))),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_r1_zero_lowers_the_target_unmodified_at_the_execute():
    ex = _ex(0, _at(TARGET_OFFSET))
    emitter = HlasmEmitter()
    lower_execute(emitter, ex, MachineStatements((ex, AR)), OPCODE_LOWERINGS["AR"])
    direct = HlasmEmitter()
    OPCODE_LOWERINGS["AR"](
        direct, AR.model_copy(update={"offset": EX_OFFSET, "length": 4})
    )

    assert (
        emitter.instructions(),
        _markers(_executed(ex, (MVC,))),
        _markers(
            _executed(
                _ex(
                    0,
                    RelocImmOperand(
                        kind="RELOC_IMM", section=SECTION, offset=TARGET_OFFSET
                    ),
                    "EXRL",
                ),
                (AR,),
            )
        ),
    ) == (
        direct.instructions(),
        [
            "MVC@2+4 {'displacement': 0, 'length': 0, 'base': 3},{'displacement': 0, 'index': 0, 'base': 12}"
        ],
        ["AR@2+6 {'value': 2},{'value': 3}"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_r1_byte_selects_one_inline_copy_per_reachable_value():
    mvc = _executed(_ex(2, _at(TARGET_OFFSET)), (MVC,))
    cli = _executed(_ex(2, _at(TARGET_OFFSET)), (CLI,))
    lhi = _executed(_ex(2, _at(TARGET_OFFSET)), (LHI,))
    mvc_lengths = [int(m.split("'length': ")[1].split(",")[0]) for m in _markers(mvc)]
    cli_immediates = [int(m.split("'value': ")[1][:-1]) for m in _markers(cli)]

    assert (
        mvc_lengths,
        len(_compared(mvc)),
        sum(1 for i in mvc if isinstance(i, BranchIf)),
        len({i.label for i in mvc if isinstance(i, Branch)}),
        sum(1 for i in mvc if isinstance(i, Branch)),
        [i.length for i in mvc if isinstance(i, LoadRegion)],
        cli_immediates,
        _compared(cli)[0],
        [m.split(" ", 1)[1] for m in _markers(lhi)],
        _abends(lhi),
        any(isinstance(i, Symbolic) for i in (*mvc, *cli, *lhi)),
    ) == (
        list(range(1, 257)),
        255,
        255,
        1,
        256,
        [4],
        [v for v in range(256) if v & 0x40],
        0xC0,
        [
            "{'value': 3},{'value': 5}",
            "{'value': 7},{'value': 5}",
            "{'value': 11},{'value': 5}",
            "{'value': 15},{'value': 5}",
        ],
        ["S0C1"],
        False,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_execute_and_specification_exceptions_abend_before_any_copy():
    inner = _ex(0, _at(0))
    inner_rl = _statement(
        "EXRL",
        "RIL-b",
        (_reg(0), RelocImmOperand(kind="RELOC_IMM", section=SECTION, offset=0)),
    )
    tbegin = _statement("TBEGIN", "SIL", (_storage(0), _imm(0)), length=6)
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
        name: (_abends(ir), _markers(ir), any(isinstance(i, LoadRegion) for i in ir))
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
        "absolute EXRL": _ex(2, _imm(TARGET_OFFSET), "EXRL"),
    }
    with caplog.at_level(logging.WARNING, logger="interpreter.hlasm.execute"):
        lowered = {name: _executed(ex, (MVC,)) for name, ex in unresolved.items()}

    assert (
        {name: (_abends(ir), _markers(ir)) for name, ir in lowered.items()},
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
