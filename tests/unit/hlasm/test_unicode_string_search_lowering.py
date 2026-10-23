# pyright: standard
"""Unicode conversion and string search lowerings: the unit widths each form reads and writes, no comparison on a byte image, the well-formedness checks M3 adds, the odd-pair checks and the GR0 check before the search reads storage."""

from collections import Counter
from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
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
)

GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
IMAGE_BUILTIN = "__int_to_binary_bytes"
COMPARISONS = frozenset(
    (
        BinopKind.EQ,
        BinopKind.NE,
        BinopKind.LT,
        BinopKind.GT,
        BinopKind.LE,
        BinopKind.GE,
    )
)
CONVERSIONS = ("CU12", "CUTFU", "CU14", "CU21", "CUUTF", "CU24", "CU41", "CU42")


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _pair(mnemonic: str, controls: Sequence[int]) -> tuple[InstructionBase, ...]:
    return _lowered(
        mnemonic,
        (reg_operand(2), reg_operand(4), *(mask_operand(m) for m in controls)),
    )


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


def _comparisons(ir: Sequence[InstructionBase]) -> list[Binop]:
    return [i for i in ir if isinstance(i, Binop) and i.operator in COMPARISONS]


def _image_comparisons(ir: Sequence[InstructionBase]) -> list[Binop]:
    images = frozenset(
        [i.result_reg for i in ir if isinstance(i, LoadRegion)]
        + [
            i.result_reg
            for i in ir
            if isinstance(i, CallFunction) and str(i.func_name) == IMAGE_BUILTIN
        ]
    )
    return [i for i in _comparisons(ir) if i.left in images or i.right in images]


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, Branch | BranchIf | Halt_ | Label_ | StoreVar)
    ]


def _load(width: int) -> tuple[str, int]:
    return ("LoadRegion", width)


def _write(width: int) -> tuple[str, int]:
    return ("WriteRegion", width)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversions_read_and_write_each_forms_units_and_compare_ints():
    lowered = {m: _pair(m, ()) for m in CONVERSIONS}
    utf8_reads = [_load(1)] * 7

    assert {m: _storage_accesses(ir) for m, ir in lowered.items()} == {
        "CU12": [*utf8_reads, _write(2), _write(4)],
        "CUTFU": [*utf8_reads, _write(2), _write(4)],
        "CU14": [*utf8_reads, _write(4)],
        "CU21": [_load(2), _load(2), _write(1), _write(2), _write(3), _write(4)],
        "CUUTF": [_load(2), _load(2), _write(1), _write(2), _write(3), _write(4)],
        "CU24": [_load(2), _load(2), _write(4)],
        "CU41": [_load(4), _write(1), _write(2), _write(3), _write(4)],
        "CU42": [_load(4), _write(2), _write(4)],
    }
    assert {m: _image_comparisons(ir) for m, ir in lowered.items()} == {
        m: [] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


def _compared_constants(ir: Sequence[InstructionBase]) -> Counter[tuple[str, int]]:
    constants = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return Counter(
        (b.operator.name, constants[b.right])
        for b in _comparisons(ir)
        if b.right in constants
    )


UTF8_CHECKS = {
    ("LT", 0xC2): 1,
    ("LT", 0xF5): 1,
    ("NE", 0x80): 6,
    ("LT", 0x800): 1,
    ("EQ", 0xD800): 1,
    ("LT", 0x10000): 1,
    ("GE", 0x110000): 1,
}
LOW_SURROGATE_CHECK = {("NE", 0xDC00): 1}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_well_formedness_control_adds_the_checks_and_other_m3_bits_do_not():
    forms = ("CU12", "CU14", "CU21", "CU24")
    added = {
        m: dict(
            _compared_constants(_pair(m, (0b0001,))) - _compared_constants(_pair(m, ()))
        )
        for m in forms
    }

    assert added == {
        "CU12": UTF8_CHECKS,
        "CU14": UTF8_CHECKS,
        "CU21": LOW_SURROGATE_CHECK,
        "CU24": LOW_SURROGATE_CHECK,
    }
    assert {m: _pair(m, (0b1110,)) == _pair(m, ()) for m in forms} == {
        m: True for m in forms
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_on_an_odd_register_abends_before_reading_any_register():
    lowered = [
        _lowered(m, (reg_operand(first), reg_operand(second)))
        for m in CONVERSIONS
        for first, second in ((3, 4), (2, 5))
    ]

    assert [
        (_storage_accesses(ir), _register_accesses(ir), _control(ir)) for ir in lowered
    ] == [([], [], [f"StoreVar:{ABEND}", "Halt_"])] * 16


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_searches_check_gr0_before_reading_storage_and_compare_ints():
    lowered = {m: _pair(m, ()) for m in ("SRST", "SRSTU")}
    first_storage_read = {
        m: next(
            n
            for n, i in enumerate(ir)
            if isinstance(i, LoadRegion) and i.region_reg not in _gprs(ir)
        )
        for m, ir in lowered.items()
    }
    abend_check = {
        m: next(n for n, i in enumerate(ir) if isinstance(i, BranchIf))
        for m, ir in lowered.items()
    }

    assert {m: _storage_accesses(ir) for m, ir in lowered.items()} == {
        "SRST": [_load(1)],
        "SRSTU": [_load(2)],
    }
    assert {m: abend_check[m] < first_storage_read[m] for m in lowered} == {
        "SRST": True,
        "SRSTU": True,
    }
    assert {m: _image_comparisons(ir) for m, ir in lowered.items()} == {
        "SRST": [],
        "SRSTU": [],
    }
    assert {
        m: _register_accesses(ir).count("WriteRegion") for m, ir in lowered.items()
    } == {
        "SRST": 1,
        "SRSTU": 1,
    }
