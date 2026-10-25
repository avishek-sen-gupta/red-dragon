# pyright: standard
"""HFP conversion lowerings: the rounding forms read M3 and the operand, call one builtin, store and set the CC with no program-mask ladder; the exact, truncating, lengthening and rounding forms are IR alone, LOAD ROUNDED abending S0CC after its store; static checks abend before any access."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    ADDRESS,
    CC,
    D8,
    SPECIFICATION,
    lowered_ir,
    registers,
    trace,
)
from tests.unit.hlasm.lowering_helpers import mask_operand, reg_operand


def _rrf(r1: int, m3: int, r2: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rounding_forms_call_the_builtin_then_store_and_set_the_cc():
    assert {
        "CFER": trace("CFER", _rrf(2, 0, 1)),
        "CGXR": trace("CGXR", _rrf(3, 7, 4)),
        "TBEDR": trace("TBEDR", _rrf(1, 3, 2)),
        "TBDR": trace("TBDR", _rrf(1, 0, 2)),
    } == {
        "CFER": ["read vr 16+4", "call hfp to_fixed_32_short", "write gpr 20+4", CC],
        "CGXR": [
            "read vr 64+8",
            "read vr 96+8",
            "call hfp to_fixed_64_extended",
            "write gpr 24+8",
            CC,
        ],
        "TBEDR": ["read vr 32+8", "call hfp to_bfp_short_long", "write vr 16+4", CC],
        "TBDR": ["read vr 32+8", "call hfp to_bfp_long_long", "write vr 16+8", CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_fixed_and_bfp_to_hfp_are_ir_without_a_call():
    assert {
        "CEFR": trace("CEFR", registers(1, 2)),
        "CXGR": trace("CXGR", registers(4, 2)),
        "THDER": trace("THDER", registers(1, 2)),
        "THDR": trace("THDR", registers(1, 2)),
    } == {
        "CEFR": ["read gpr 20+4", "write vr 16+4"],
        "CXGR": ["read gpr 16+8", "write vr 64+8", "write vr 96+8"],
        "THDER": ["read vr 32+4", "write vr 16+8", CC],
        "THDR": ["read vr 32+8", "write vr 16+8", CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lengthening_is_ir_and_rounding_stores_before_the_overflow_abend():
    overflow = "StoreVar __hlasm_abend S0CC"

    assert {
        "LDER": trace("LDER", registers(1, 2)),
        "LXD": trace("LXD", (reg_operand(4), D8)),
        "LEDR": trace("LEDR", registers(1, 2)),
        "LEXR": trace("LEXR", registers(1, 4)),
    } == {
        "LDER": ["read vr 32+4", "write vr 16+8"],
        "LXD": [ADDRESS, "read storage +8", "write vr 64+8", "write vr 96+8"],
        "LEDR": ["read vr 32+8", "write vr 16+4", overflow],
        "LEXR": ["read vr 64+8", "read vr 96+8", "write vr 16+4", overflow],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_and_modifiers_abend_before_any_access():
    traces = [
        trace("CFER", _rrf(2, 3, 1)),
        trace("CGDR", _rrf(2, 2, 1)),
        trace("CFDR", _rrf(2, 8, 1)),
        trace("CFXR", _rrf(2, 0, 2)),
        trace("CGXR", _rrf(2, 4, 7)),
        trace("TBEDR", _rrf(1, 2, 2)),
        trace("TBDR", _rrf(1, 8, 2)),
        trace("CXFR", registers(2, 1)),
        trace("CXGR", registers(7, 1)),
        trace("LXDR", registers(2, 1)),
        trace("LXD", (reg_operand(3), D8)),
        trace("LXER", registers(6, 0)),
        trace("LXE", (reg_operand(2), D8)),
        trace("LDXR", registers(1, 2)),
        trace("LRDR", registers(1, 6)),
        trace("LEXR", registers(0, 3)),
    ]

    assert traces == [[SPECIFICATION]] * len(traces)


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CFER CFDR CFXR CGER CGDR CGXR": _rrf(1, 4, 4),
    "TBEDR TBDR": _rrf(1, 1, 4),
    "CEFR CDFR CXFR CEGR CDGR CXGR THDER THDR": registers(4, 2),
    "LDER LXDR LXER LEDR LRER LDXR LRDR LEXR": registers(4, 8),
    "LDE LXD LXE": (reg_operand(4), D8),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 27
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
