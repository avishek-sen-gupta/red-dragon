# pyright: standard
"""BFP conversion lowerings: rounding forms read the mode and operand, call one builtin and run the trap ladder; exact forms and lengthening are IR alone; static checks abend before any access."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    ADDRESS,
    CC,
    D8,
    READ_FPC,
    SPECIFICATION,
    ladder,
    lowered_ir,
    registers,
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
            "read vr 16+8",
            "call to_fixed_32_long",
            *ladder("write gpr 20+4", CC),
        ],
        "CGEBRA": [
            "read vr 16+4",
            "call to_fixed_64_short",
            *ladder("write gpr 24+8", CC),
        ],
        "CLGXBR": [
            "read vr 64+8",
            "read vr 96+8",
            "call to_logical_64_extended",
            *ladder("write gpr 16+8", CC),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_fixed_rounds_through_the_builtin_unless_the_target_is_wide_enough():
    assert {
        "CEFBR": trace("CEFBR", registers(1, 2)),
        "CDLGBR": trace("CDLGBR", _rrfe(1, 5, 2, 0)),
        "CDFBR": trace("CDFBR", registers(1, 2)),
        "CXLGBR": trace("CXLGBR", _rrfe(4, 0, 2, 0)),
    } == {
        "CEFBR": [
            READ_FPC,
            "read gpr 20+4",
            "call from_fixed_short",
            *ladder("write vr 16+4"),
        ],
        "CDLGBR": ["read gpr 16+8", "call from_fixed_long", *ladder("write vr 16+8")],
        "CDFBR": ["read gpr 20+4", "write vr 16+8"],
        "CXLGBR": ["read gpr 16+8", "write vr 64+8", "write vr 96+8"],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lengthening_is_ir_and_rounding_merges_into_the_source_format_register():
    assert {
        "LDEBR": trace("LDEBR", registers(1, 2)),
        "LXEB": trace("LXEB", (reg_operand(4), D8)),
        "LEDBR": trace("LEDBR", registers(1, 2)),
        "LEXBRA": trace("LEXBRA", _rrfe(4, 5, 8, 4)),
    } == {
        "LDEBR": ["read vr 32+4", *ladder("write vr 16+8")],
        "LXEB": [
            ADDRESS,
            "read storage +4",
            *ladder("write vr 64+8", "write vr 96+8"),
        ],
        "LEDBR": [
            READ_FPC,
            "read vr 32+8",
            "call rounded_to_short_long",
            *ladder("read vr 16+8", "write vr 16+8"),
        ],
        "LEXBRA": [
            "read vr 128+8",
            "read vr 160+8",
            "call rounded_to_short_extended",
            *ladder("read vr 64+8", "read vr 96+8", "write vr 64+8", "write vr 96+8"),
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
        trace("CXFBR", registers(2, 1)),
        trace("CXLGBR", _rrfe(6, 0, 1, 0)),
        trace("CDFBRA", _rrfe(1, 2, 1, 0)),
        trace("CELFBR", _rrfe(1, 9, 1, 0)),
        trace("LXDBR", registers(2, 1)),
        trace("LXEB", (reg_operand(3), D8)),
        trace("LDXBR", registers(0, 2)),
        trace("LEXBR", registers(2, 0)),
        trace("LEDBRA", _rrfe(1, 2, 2, 0)),
    ]

    assert traces == [[SPECIFICATION]] * len(traces)


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CFEBR CFDBR CFXBR CGEBR CGDBR CGXBR": _rrf(1, 0, 4),
    "CFEBRA CFDBRA CFXBRA CGEBRA CGDBRA CGXBRA": _rrfe(1, 0, 4, 4),
    "CLFEBR CLFDBR CLFXBR CLGEBR CLGDBR CLGXBR": _rrfe(1, 5, 4, 0),
    "CEFBR CDFBR CXFBR CEGBR CDGBR CXGBR": registers(4, 2),
    "CEFBRA CDFBRA CXFBRA CEGBRA CDGBRA CXGBRA": _rrfe(4, 0, 2, 4),
    "CELFBR CDLFBR CXLFBR CELGBR CDLGBR CXLGBR": _rrfe(4, 1, 2, 0),
    "LDEBR LXDBR LXEBR LEDBR LDXBR LEXBR": registers(4, 1),
    "LDEB LXDB LXEB": (reg_operand(4), D8),
    "LEDBRA LDXBRA LEXBRA": _rrfe(4, 3, 1, 4),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 48
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
