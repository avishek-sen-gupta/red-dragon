# pyright: standard
"""Translate lowerings: one unit and one function per loop iteration at the widths each form selects, stores only where the form translates, no comparison on a byte image, and the odd-pair checks."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
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
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
LOOP_AT = "__hlasm_ss_at"
IMAGE_BUILTIN = "__int_to_binary_bytes"
COMPARISONS = frozenset((BinopKind.EQ, BinopKind.NE, BinopKind.LT, BinopKind.GT))


def _with_length(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=displacement, length=length, base=BASE
    )


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
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
    ir = _lowered("TR", (_with_length(8, 256), storage_operand(300)))
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
        "TRT": _lowered("TRT", (_with_length(8, 4), storage_operand(300))),
        "TRTR": _lowered("TRTR", (_with_length(8, 4), storage_operand(300))),
        "TRE": _lowered("TRE", (reg_operand(2), reg_operand(4))),
        "TROO": _lowered("TROO", (reg_operand(2), reg_operand(4))),
        "TROT": _lowered("TROT", (reg_operand(2), reg_operand(4))),
        "TRTO": _lowered("TRTO", (reg_operand(2), reg_operand(4))),
        "TRTT": _lowered("TRTT", (reg_operand(2), reg_operand(4), mask_operand(0))),
        "TRTE": _lowered("TRTE", (reg_operand(2), reg_operand(4))),
        "TRTE A F": _lowered(
            "TRTE", (reg_operand(2), reg_operand(4), mask_operand(12))
        ),
        "TRTRE F": _lowered("TRTRE", (reg_operand(2), reg_operand(4), mask_operand(4))),
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
    compared = _lowered("TROO", (reg_operand(2), reg_operand(4)))
    uncompared = _lowered("TROO", (reg_operand(2), reg_operand(4), mask_operand(1)))

    assert (_equal_tests(compared), _equal_tests(uncompared)) == (1, 0)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pair_translates_on_an_odd_register_abend_before_reading_any_register():
    lowered = [
        _lowered("TRE", (reg_operand(3), reg_operand(4))),
        _lowered("TROO", (reg_operand(3), reg_operand(4))),
        _lowered("TRTT", (reg_operand(5), reg_operand(2), mask_operand(1))),
        _lowered("TRTE", (reg_operand(5), reg_operand(4))),
        _lowered("TRTRE", (reg_operand(3), reg_operand(2), mask_operand(12))),
    ]

    assert [
        (_storage_accesses(ir), _register_accesses(ir), _control(ir)) for ir in lowered
    ] == [([], [], [f"StoreVar:{ABEND}", "Halt_"])] * 5
