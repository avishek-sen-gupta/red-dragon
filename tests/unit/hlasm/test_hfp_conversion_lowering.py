# pyright: standard
"""HFP conversion lowerings: the rounding forms read M3 and the operand, call one builtin, store and set the CC with no program-mask ladder; static checks abend before any access."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    CC,
    SPECIFICATION,
    lowered_ir,
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
        "CFER": ["read fpr 8+4", "call hfp to_fixed_32_short", "write gpr 20+4", CC],
        "CGXR": [
            "read fpr 32+8",
            "read fpr 48+8",
            "call hfp to_fixed_64_extended",
            "write gpr 24+8",
            CC,
        ],
        "TBEDR": ["read fpr 16+8", "call hfp to_bfp_short_long", "write fpr 8+4", CC],
        "TBDR": ["read fpr 16+8", "call hfp to_bfp_long_long", "write fpr 8+8", CC],
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
    ]

    assert traces == [[SPECIFICATION]] * len(traces)


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CFER CFDR CFXR CGER CGDR CGXR": _rrf(1, 4, 4),
    "TBEDR TBDR": _rrf(1, 1, 4),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 8
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
