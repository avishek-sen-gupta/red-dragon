# pyright: standard
"""Boolean lowerings: the operand widths they read and write, the field they replace, the CC, and the storage-to-storage byte loop."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
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
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    machine_statement,
    reg_operand,
    storage_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
CC = "__hlasm_cc"
AT = "__hlasm_ss_at"
ANY = "__hlasm_ss_any"


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
        "NRK": _lowered(
            machine_statement("NRK", (reg_operand(5), reg_operand(3), reg_operand(4)))
        ),
        "NG": _lowered(machine_statement("NG", (reg_operand(2), storage_operand(8)))),
        "NNGRK": _lowered(
            machine_statement("NNGRK", (reg_operand(5), reg_operand(3), reg_operand(4)))
        ),
        "XI": _lowered(
            machine_statement("XI", (storage_operand(8), imm_operand(0x0F)))
        ),
        "NIHH": _lowered(
            machine_statement("NIHH", (reg_operand(2), imm_operand(0xFEDC)))
        ),
        "XILF": _lowered(machine_statement("XILF", (reg_operand(2), imm_operand(-1)))),
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
def test_storage_to_storage_forms_are_one_byte_loop_of_at_least_one_byte():
    short = _lowered(machine_statement("NC", (_with_length(8, 1), storage_operand(40))))
    explicit_zero = _lowered(
        machine_statement("OC", (_with_length(8, 0), storage_operand(40)))
    )
    longest = _lowered(
        machine_statement("XC", (_with_length(8, 256), storage_operand(40)))
    )

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
            f"StoreVar:{ANY}",
            f"StoreVar:{AT}",
            "Label_",
            "BranchIf",
            "Label_",
            f"StoreVar:{ANY}",
            f"StoreVar:{AT}",
            "Branch",
            "Label_",
            f"StoreVar:{CC}",
        ],
    )
    assert (_bounds(short), _bounds(explicit_zero), _bounds(longest)) == (
        [1],
        [1],
        [256],
    )
    assert [i for i in longest if isinstance(i, Symbolic)] == []
