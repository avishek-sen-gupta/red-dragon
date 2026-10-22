# pyright: standard
"""Interlocked-update lowerings: the boundary check before any operand, one compare that swaps or reloads, CAL's second operand checked only when it is loaded, the load-and-operate stores in PoO order with the overflow check, TS, and odd pair registers abending S0C6 before any read."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.locked_operations import LOCKED_OPERATIONS
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.hlasm.opcodes.interlocked import INTERLOCKED_LOWERINGS
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
from interpreter.operator_kind import BinopKind
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    describe,
    machine_statement,
    reg_operand,
    storage_operand,
)

GPRS = "LoadVar __hlasm_gprs"
SPECIFICATION_ABEND = ["StoreVar __hlasm_abend S0C6", "Halt_"]
WORD_BOUNDARY_CHECK = ["& 3", "!= 0", "BranchIf", *SPECIFICATION_ABEND]
SECOND_ADDRESS = ["LoadRegion 100+4", "+ reg", "& 2147483647"]
RS_OPERANDS: Sequence[Operand] = (reg_operand(4), reg_operand(6), storage_operand(8))
SSF_OPERANDS: Sequence[Operand] = (
    reg_operand(4),
    storage_operand(8),
    storage_operand(16),
)

PLO_OPERANDS: Sequence[Operand] = (
    reg_operand(4),
    storage_operand(8),
    reg_operand(6),
    storage_operand(16),
)


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _shape(
    ir: Sequence[InstructionBase], kinds: tuple[type[InstructionBase], ...]
) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    described = (describe(i, consts) for i in ir if isinstance(i, kinds))
    return [line for line in described if line != GPRS]


ACCESSES = (LoadVar, StoreVar, BranchIf, Branch, LoadRegion, WriteRegion, Binop, Halt_)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compare_and_swap_checks_the_boundary_then_swaps_or_reloads():
    ir = _lowered("CS", (reg_operand(4), reg_operand(5), storage_operand(8)))

    assert _shape(ir, ACCESSES) == [
        *SECOND_ADDRESS,
        *WORD_BOUNDARY_CHECK,
        "LoadRegion 36+4",
        "LoadRegion 0+4",
        "!= reg",
        "BranchIf",
        "% 4294967296",
        "WriteRegion 36+4",
        "StoreVar __hlasm_cc 1",
        "Branch hl_compared_2",
        "LoadRegion 44+4",
        "% 4294967296",
        "WriteRegion 0+4",
        "StoreVar __hlasm_cc 0",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compare_and_load_checks_the_second_operand_only_when_it_is_loaded():
    ir = _lowered("CAL", SSF_OPERANDS)

    assert _shape(ir, ACCESSES) == [
        *SECOND_ADDRESS,
        *WORD_BOUNDARY_CHECK,
        *SECOND_ADDRESS,
        "LoadRegion 36+4",
        "LoadRegion 0+4",
        "!= reg",
        "BranchIf",
        "% 4294967296",
        "WriteRegion 36+4",
        "StoreVar __hlasm_cc 1",
        "Branch hl_compared_2",
        *WORD_BOUNDARY_CHECK,
        "LoadRegion 0+4",
        "% 4294967296",
        "WriteRegion 36+4",
        "StoreVar __hlasm_cc 0",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_and_operate_stores_the_result_then_the_original_and_only_signed_add_checks_overflow():
    effects = (WriteRegion, StoreVar, LoadVar, Halt_)
    stores = ["WriteRegion 0+4", "WriteRegion 36+4", "StoreVar __hlasm_cc reg"]
    unchecked = [*SPECIFICATION_ABEND, *stores]

    assert {
        mnemonic: _shape(_lowered(mnemonic, RS_OPERANDS), effects)
        for mnemonic in ("LAA", "LAAL", "LAN", "LAO", "LAX")
    } == {
        "LAA": [
            *unchecked,
            "LoadVar __hlasm_pm",
            "StoreVar __hlasm_abend S0C8",
            "Halt_",
        ],
        "LAAL": unchecked,
        "LAN": unchecked,
        "LAO": unchecked,
        "LAX": unchecked,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_test_and_set_takes_the_cc_from_bit_0_and_stores_all_ones():
    ir = _lowered("TS", (storage_operand(8),))
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}

    assert _shape(ir, ACCESSES) == [
        *SECOND_ADDRESS,
        "LoadRegion 0+1",
        "% 256",
        "WriteRegion 0+1",
        ">> 7",
        "StoreVar __hlasm_cc reg",
    ]
    assert [
        consts[i.left]
        for i in ir
        if isinstance(i, Binop) and i.operator == BinopKind.MOD
    ] == [255]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_odd_pair_registers_abend_s0c6_before_any_register_is_read():
    odd: dict[str, tuple[str, Sequence[Operand]]] = {
        "CDS odd R1": ("CDS", (reg_operand(5), reg_operand(6), storage_operand(8))),
        "CDSY odd R3": ("CDSY", (reg_operand(4), reg_operand(7), storage_operand(8))),
        "CDSG odd R1": ("CDSG", (reg_operand(5), reg_operand(6), storage_operand(8))),
        "LPD": ("LPD", (reg_operand(5), storage_operand(8), storage_operand(16))),
        "LPDG": ("LPDG", (reg_operand(3), storage_operand(8), storage_operand(16))),
        "LPQ": ("LPQ", (reg_operand(5), storage_operand(16))),
        "STPQ": ("STPQ", (reg_operand(7), storage_operand(16))),
    }

    assert {
        case: [type(i).__name__ for i in _lowered(mnemonic, operands)]
        for case, (mnemonic, operands) in odd.items()
    } == {case: ["Const", "StoreVar", "Halt_"] for case in odd}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_interlocked_mnemonic_lowers_without_symbolic():
    operands: dict[str, Sequence[Operand]] = {
        "CSST": (storage_operand(8), storage_operand(16), reg_operand(4)),
        "PLO": PLO_OPERANDS,
        "LPQ": (reg_operand(4), storage_operand(16)),
        "STPQ": (reg_operand(4), storage_operand(16)),
        "TS": (storage_operand(8),),
        **{m: SSF_OPERANDS for m in ("CAL", "CALGF", "CALG", "LPD", "LPDG")},
    }

    assert {
        mnemonic: any(
            isinstance(i, Symbolic)
            for i in _lowered(mnemonic, operands.get(mnemonic, RS_OPERANDS))
        )
        for mnemonic in INTERLOCKED_LOWERINGS
    } == {mnemonic: False for mnemonic in INTERLOCKED_LOWERINGS}


WIDTHS = (4, 8, 16, 32)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_plo_table_has_a_row_per_function_code_with_its_figure_7_380_shape():
    expected = {
        0: (4, 1, 1, ()),
        1: (8, 1, 1, ()),
        2: (8, 1, 1, ()),
        3: (16, 1, 1, ()),
        4: (4, 1, 1, (0,)),
        5: (8, 1, 1, ()),
        6: (8, 1, 1, (0,)),
        7: (16, 1, 1, ()),
        8: (4, 2, 2, (0, 2)),
        9: (8, 2, 2, ()),
        10: (8, 2, 2, (0, 2)),
        11: (16, 2, 2, ()),
        12: (4, 1, 2, (0,)),
        13: (8, 1, 2, ()),
        14: (8, 1, 2, (0,)),
        15: (16, 1, 2, ()),
        16: (4, 1, 3, (0,)),
        17: (8, 1, 3, ()),
        18: (8, 1, 3, (0,)),
        19: (16, 1, 3, ()),
        20: (4, 1, 4, (0,)),
        21: (8, 1, 4, ()),
        22: (8, 1, 4, (0,)),
        23: (16, 1, 4, ()),
        24: (32, 1, 1, ()),
        25: (32, 1, 1, ()),
        26: (32, 2, 2, ()),
        27: (32, 1, 2, ()),
        28: (32, 1, 3, ()),
        29: (32, 1, 4, ()),
        **{30 + k: (w, 3, 3, ()) for k, w in enumerate(WIDTHS)},
        **{34 + k: (w, 4, 4, ()) for k, w in enumerate(WIDTHS)},
        38: (32, 0, 1, ()),
        39: (16, 0, 2, ()),
        40: (32, 0, 2, ()),
        **{41 + k: (w, 0, 3, ()) for k, w in enumerate(WIDTHS)},
        **{45 + k: (w, 0, 4, ()) for k, w in enumerate(WIDTHS)},
        49: (32, 0, 1, ()),
        **{50 + k: (w, 0, 2, ()) for k, w in enumerate(WIDTHS)},
        **{54 + k: (w, 0, 3, ()) for k, w in enumerate(WIDTHS)},
        **{58 + k: (w, 0, 4, ()) for k, w in enumerate(WIDTHS)},
    }

    assert {
        code: (row.width, len(row.compares), len(row.stores), row.even_registers)
        for code, row in LOCKED_OPERATIONS.items()
    } == expected


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_plo_checks_gr0_and_the_test_bit_before_selecting_one_block_per_function_code():
    ir = _lowered("PLO", PLO_OPERANDS)
    shape = _shape(ir, ACCESSES)

    assert shape[:22] == [
        "LoadRegion 4+4",
        ">> 9",
        "!= 0",
        "BranchIf",
        *SPECIFICATION_ABEND,
        "& 255",
        ">> 8",
        "!= 0",
        "BranchIf",
        "<= 61",
        "BranchIf",
        "StoreVar __hlasm_cc 0",
        "Branch hl_either_7",
        "StoreVar __hlasm_cc 3",
        "Branch hl_either_4",
        "> 61",
        "BranchIf",
        *SPECIFICATION_ABEND,
        "LoadRegion 100+4",
        "+ reg",
    ]
    assert (
        sum(1 for i in ir if isinstance(i, Binop) and i.operator == BinopKind.LT) == 61
    )
