# pyright: standard
"""Translate lowerings: one unit and one function per loop iteration at the widths each form selects, stores only where the form translates, no comparison on a byte image, and the odd-pair checks."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
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
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

BASE = 12
GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
LOOP_AT = "__hlasm_ss_at"
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


def _mask(value: int) -> MaskOperand:
    return MaskOperand(kind="MASK", value=value)


def _with_length(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=displacement, length=length, base=BASE
    )


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, _statement(mnemonic, operands))
    return emitter.instructions()


def _gprs(ir: Sequence[InstructionBase]) -> frozenset[Register]:
    return frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )


def _storage_accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, int]]:
    gprs = _gprs(ir)
    return [
        (type(i).__name__, i.length)
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion) and i.region_reg not in gprs
    ]


def _register_accesses(ir: Sequence[InstructionBase]) -> list[str]:
    gprs = _gprs(ir)
    return [
        type(i).__name__
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion) and i.region_reg in gprs
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


def _equal_tests(ir: Sequence[InstructionBase]) -> int:
    return len([i for i in ir if isinstance(i, Binop) and i.operator == BinopKind.EQ])


def _symbolic(lowered: Sequence[Sequence[InstructionBase]]) -> list[InstructionBase]:
    return [i for ir in lowered for i in ir if isinstance(i, Symbolic)]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_tr_translates_one_byte_per_iteration_and_leaves_the_cc_and_registers():
    ir = _lowered("TR", (_with_length(8, 256), _storage(300)))
    consts = [i.value for i in ir if isinstance(i, Const)]

    assert (
        _storage_accesses(ir),
        _register_accesses(ir),
        _control(ir),
        256 in consts,
    ) == (
        [("LoadRegion", 1), ("LoadRegion", 1), ("WriteRegion", 1)],
        ["LoadRegion", "LoadRegion"],
        [
            f"StoreVar:{LOOP_AT}",
            "Label_",
            "BranchIf",
            "Label_",
            f"StoreVar:{LOOP_AT}",
            "Branch",
            "Label_",
        ],
        True,
    )
    assert _symbolic([ir]) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_translate_loops_read_each_forms_unit_widths_and_compare_ints():
    lowered = {
        "TRT": _lowered("TRT", (_with_length(8, 4), _storage(300))),
        "TRTR": _lowered("TRTR", (_with_length(8, 4), _storage(300))),
        "TRE": _lowered("TRE", (_reg(2), _reg(4))),
        "TROO": _lowered("TROO", (_reg(2), _reg(4))),
        "TROT": _lowered("TROT", (_reg(2), _reg(4))),
        "TRTO": _lowered("TRTO", (_reg(2), _reg(4))),
        "TRTT": _lowered("TRTT", (_reg(2), _reg(4), _mask(0))),
        "TRTE": _lowered("TRTE", (_reg(2), _reg(4))),
        "TRTE A F": _lowered("TRTE", (_reg(2), _reg(4), _mask(12))),
        "TRTRE F": _lowered("TRTRE", (_reg(2), _reg(4), _mask(4))),
    }

    assert {m: _storage_accesses(ir) for m, ir in lowered.items()} == {
        "TRT": [("LoadRegion", 1), ("LoadRegion", 1)],
        "TRTR": [("LoadRegion", 1), ("LoadRegion", 1)],
        "TRE": [("LoadRegion", 1), ("LoadRegion", 1), ("WriteRegion", 1)],
        "TROO": [("LoadRegion", 1), ("LoadRegion", 1), ("WriteRegion", 1)],
        "TROT": [("LoadRegion", 1), ("LoadRegion", 2), ("WriteRegion", 2)],
        "TRTO": [("LoadRegion", 2), ("LoadRegion", 1), ("WriteRegion", 1)],
        "TRTT": [("LoadRegion", 2), ("LoadRegion", 2), ("WriteRegion", 2)],
        "TRTE": [("LoadRegion", 1), ("LoadRegion", 1)],
        "TRTE A F": [("LoadRegion", 2), ("LoadRegion", 2)],
        "TRTRE F": [("LoadRegion", 1), ("LoadRegion", 2)],
    }
    assert {m: _image_comparisons(ir) for m, ir in lowered.items()} == {
        m: [] for m in lowered
    }
    assert _symbolic(list(lowered.values())) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_test_character_control_drops_the_comparison():
    compared = _lowered("TROO", (_reg(2), _reg(4)))
    uncompared = _lowered("TROO", (_reg(2), _reg(4), _mask(1)))

    assert (_equal_tests(compared), _equal_tests(uncompared)) == (1, 0)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pair_translates_on_an_odd_register_abend_before_reading_any_register():
    lowered = [
        _lowered("TRE", (_reg(3), _reg(4))),
        _lowered("TROO", (_reg(3), _reg(4))),
        _lowered("TRTT", (_reg(5), _reg(2), _mask(1))),
        _lowered("TRTE", (_reg(5), _reg(4))),
        _lowered("TRTRE", (_reg(3), _reg(2), _mask(12))),
    ]

    assert [
        (_storage_accesses(ir), _register_accesses(ir), _control(ir)) for ir in lowered
    ] == [([], [], [f"StoreVar:{ABEND}", "Halt_"])] * 5
