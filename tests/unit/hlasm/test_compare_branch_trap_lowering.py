# pyright: standard
"""Compare-and-branch, compare-and-trap and load-and-trap lowerings: the comparison's CC tested against M3 and never stored, the branch or S0C7 trap, and the load written before its zero test."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Branch,
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
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    describe,
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)

BASE = 12


def _relative(offset: int) -> RelocImmOperand:
    return RelocImmOperand(kind="RELOC_IMM", section="T", offset=offset)


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _shape(ir: Sequence[InstructionBase]) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        describe(i, consts)
        for i in ir
        if isinstance(
            i,
            (
                LoadVar,
                StoreVar,
                BranchIf,
                Branch,
                LoadRegion,
                WriteRegion,
                Binop,
                Halt_,
                Symbolic,
            ),
        )
    ]


def _gpr(r: int, width: int) -> list[str]:
    return ["LoadVar __hlasm_gprs", f"LoadRegion {8 * r + 8 - width}+{width}"]


def _mask_test(mask: int) -> list[str]:
    return [">> reg", f"& {mask}", "!= 0", "BranchIf"]


def _tail_from_mask_test(shape: Sequence[str]) -> list[str]:
    return list(shape[shape.index(">> reg") :])


RELATIVE_40 = ["LoadVar __hlasm_sect_T", "+ 40"]
STORAGE_16 = [*_gpr(BASE, 4), "+ reg", "& 2147483647"]
DISPATCH = ["StoreVar __hlasm_target reg", "Branch hl_dispatch"]
TRAP = ["StoreVar __hlasm_abend S0C7", "Halt_"]
WRAP_64 = "% 18446744073709551616"


def _sets_cc_or_symbolic(ir: Sequence[InstructionBase]) -> list[InstructionBase]:
    return [
        i
        for i in ir
        if isinstance(i, Symbolic)
        or (isinstance(i, StoreVar) and i.name == "__hlasm_cc")
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_conditional_compare_tests_its_m3_bit_then_branches_or_traps():
    lowered = {
        "CRJ": _lowered(
            "CRJ", (reg_operand(3), reg_operand(5), mask_operand(4), _relative(40))
        ),
        "CGRB": _lowered(
            "CGRB",
            (reg_operand(3), reg_operand(5), mask_operand(10), storage_operand(16)),
        ),
        "CLIJ": _lowered(
            "CLIJ", (reg_operand(3), imm_operand(200), mask_operand(8), _relative(40))
        ),
        "CGIB": _lowered(
            "CGIB",
            (reg_operand(3), imm_operand(-3), mask_operand(2), storage_operand(16)),
        ),
        "CRT": _lowered("CRT", (reg_operand(3), reg_operand(5), mask_operand(6))),
        "CLGIT": _lowered("CLGIT", (reg_operand(3), imm_operand(9), mask_operand(12))),
        "CLT": _lowered("CLT", (reg_operand(3), mask_operand(8), storage_operand(16))),
    }
    shapes = {name: _shape(ir) for name, ir in lowered.items()}

    assert {name: shape[:4] for name, shape in shapes.items()} == {
        "CRJ": [*_gpr(3, 4), *_gpr(5, 4)],
        "CGRB": [*_gpr(3, 8), *_gpr(5, 8)],
        "CLIJ": [*_gpr(3, 4), "% 4294967296", "% 4294967296"],
        "CGIB": [*_gpr(3, 8), "+ 128", "% 256"],
        "CRT": [*_gpr(3, 4), *_gpr(5, 4)],
        "CLGIT": [*_gpr(3, 8), WRAP_64, WRAP_64],
        "CLT": [*_gpr(3, 4), *_gpr(BASE, 4)],
    }
    assert {name: _tail_from_mask_test(shape) for name, shape in shapes.items()} == {
        "CRJ": [*_mask_test(4), *RELATIVE_40, *DISPATCH],
        "CGRB": [*_mask_test(10), *STORAGE_16, *DISPATCH],
        "CLIJ": [*_mask_test(8), *RELATIVE_40, *DISPATCH],
        "CGIB": [*_mask_test(2), *STORAGE_16, *DISPATCH],
        "CRT": [*_mask_test(6), *TRAP],
        "CLGIT": [*_mask_test(12), *TRAP],
        "CLT": [*_mask_test(8), *TRAP],
    }
    assert [_sets_cc_or_symbolic(ir) for ir in lowered.values()] == [[]] * len(lowered)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mask_zero_lowers_to_nothing_and_mask_fourteen_acts_without_comparing():
    nothing = [
        _lowered(
            "CRJ", (reg_operand(3), reg_operand(5), mask_operand(0), _relative(40))
        ),
        _lowered(
            "CLIB",
            (reg_operand(3), imm_operand(7), mask_operand(0), storage_operand(16)),
        ),
        _lowered("CGRT", (reg_operand(3), reg_operand(5), mask_operand(0))),
        _lowered("CLGT", (reg_operand(3), mask_operand(0), storage_operand(16))),
        _lowered("CIT", (reg_operand(3), imm_operand(1), mask_operand(1))),
    ]
    always = {
        "CRJ": _lowered(
            "CRJ", (reg_operand(3), reg_operand(5), mask_operand(14), _relative(40))
        ),
        "CIB": _lowered(
            "CIB",
            (reg_operand(3), imm_operand(7), mask_operand(15), storage_operand(16)),
        ),
        "CLRT": _lowered("CLRT", (reg_operand(3), reg_operand(5), mask_operand(14))),
        "CLT": _lowered("CLT", (reg_operand(3), mask_operand(14), storage_operand(16))),
    }

    assert nothing == [()] * len(nothing)
    assert {name: _shape(ir) for name, ir in always.items()} == {
        "CRJ": [*RELATIVE_40, *DISPATCH],
        "CIB": [*STORAGE_16, *DISPATCH],
        "CLRT": TRAP,
        "CLT": TRAP,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_and_trap_writes_the_register_then_traps_on_zero():
    shapes = {
        name: _shape(_lowered(name, (reg_operand(3), storage_operand(16))))
        for name in ("LAT", "LGAT", "LLGFAT", "LLGTAT")
    }
    stored_64 = ["LoadVar __hlasm_gprs", WRAP_64, "WriteRegion 24+8"]
    zero_test = ["== 0", "BranchIf", *TRAP]

    assert shapes == {
        "LAT": [
            *STORAGE_16,
            "LoadRegion 0+4",
            "LoadVar __hlasm_gprs",
            "% 4294967296",
            "WriteRegion 28+4",
            *zero_test,
        ],
        "LGAT": [*STORAGE_16, "LoadRegion 0+8", *stored_64, *zero_test],
        "LLGFAT": [*STORAGE_16, "LoadRegion 0+4", *stored_64, *zero_test],
        "LLGTAT": [
            *STORAGE_16,
            "LoadRegion 0+4",
            "& 2147483647",
            *stored_64,
            *zero_test,
        ],
    }
