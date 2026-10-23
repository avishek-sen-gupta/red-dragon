# pyright: standard
"""BFP conversion lowerings: rounding forms read the mode and operand, call one builtin and run the trap ladder; exact forms and lengthening are IR alone; static checks abend before any access."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.bfp_trace import (
    CC,
    READ_FPC,
    SPECIFICATION,
    ladder,
    lowered_ir,
    trace,
)
from tests.unit.hlasm.lowering_helpers import mask_operand, reg_operand


def _rrfe(r1: int, m3: int, r2: int, m4: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2), mask_operand(m4))


def _rrf(r1: int, m3: int, r2: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_fixed_forms_call_the_builtin_then_store_the_gr_and_cc():
    assert {
        "CFDBR": trace("CFDBR", _rrf(2, 0, 1)),
        "CGEBRA": trace("CGEBRA", _rrfe(3, 5, 1, 4)),
        "CLGXBR": trace("CLGXBR", _rrfe(2, 7, 4, 0)),
    } == {
        "CFDBR": [
            READ_FPC,
            "read fpr 8+8",
            "call to_fixed_32_long",
            *ladder("write gpr 20+4", CC),
        ],
        "CGEBRA": [
            "read fpr 8+4",
            "call to_fixed_64_short",
            *ladder("write gpr 24+8", CC),
        ],
        "CLGXBR": [
            "read fpr 32+8",
            "read fpr 48+8",
            "call to_logical_64_extended",
            *ladder("write gpr 16+8", CC),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_and_modifiers_abend_before_any_access():
    traces = [
        trace("CFDBR", _rrf(2, 2, 1)),
        trace("CGEBRA", _rrfe(2, 8, 1, 0)),
        trace("CFXBR", _rrf(2, 0, 2)),
        trace("CLGXBR", _rrfe(2, 0, 6, 0)),
        trace("CLFEBR", _rrfe(2, 15, 1, 0)),
    ]

    assert traces == [[SPECIFICATION]] * len(traces)


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CFEBR CFDBR CFXBR CGEBR CGDBR CGXBR": _rrf(1, 0, 4),
    "CFEBRA CFDBRA CFXBRA CGEBRA CGDBRA CGXBRA": _rrfe(1, 0, 4, 4),
    "CLFEBR CLFDBR CLFXBR CLGEBR CLGDBR CLGXBR": _rrfe(1, 5, 4, 0),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 18
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
