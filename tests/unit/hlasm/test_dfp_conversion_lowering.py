# pyright: standard
"""DFP conversion lowerings: the rounding forms read the mode and the operand, call one builtin and run the trap ladder; invalid pairs abend before any access; no SYMBOLIC."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    CC,
    READ_FPC,
    SPECIFICATION,
    ladder,
    lowered_ir,
    registers,
    trace,
)
from tests.unit.hlasm.lowering_helpers import mask_operand, reg_operand

DECODE_LONG = "call dfp decode_long"
DECODE_EXTENDED = "call dfp decode_extended"
ENCODE_LONG = "call dfp encode_long"
ENCODE_EXTENDED = "call dfp encode_extended"


def _rrfe(r1: int, m3: int, r2: int, m4: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2), mask_operand(m4))


def _rrf(r1: int, m3: int, r2: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fixed_point_forms_call_the_builtin_then_store_through_the_ladder():
    assert {
        "CGDTR": trace("CGDTR", _rrf(2, 0, 1)),
        "CLFXTR": trace("CLFXTR", _rrfe(2, 1, 4, 0)),
        "CDGTR": trace("CDGTR", registers(1, 2)),
        "CXLFTR": trace("CXLFTR", _rrfe(4, 0, 2, 0)),
        "CDLGTR": trace("CDLGTR", _rrfe(1, 5, 2, 4)),
    } == {
        "CGDTR": [
            READ_FPC,
            "read fpr 8+8",
            DECODE_LONG,
            "call dfp to_fixed_64_long",
            *ladder("write gpr 16+8", CC),
        ],
        "CLFXTR": [
            "read fpr 32+8",
            "read fpr 48+8",
            DECODE_EXTENDED,
            "call dfp to_logical_32_extended",
            *ladder("write gpr 20+4", CC),
        ],
        "CDGTR": [
            READ_FPC,
            "read gpr 16+8",
            "call dfp from_fixed_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
        "CXLFTR": [
            READ_FPC,
            "read gpr 20+4",
            "call dfp from_fixed_extended",
            *ladder(ENCODE_EXTENDED, "write fpr 32+8", "write fpr 48+8"),
        ],
        "CDLGTR": [
            "read gpr 16+8",
            "call dfp from_fixed_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_abend_before_any_access():
    traces = [
        trace("CXFTR", _rrfe(2, 0, 1, 0)),
        trace("CXGTR", registers(6, 1)),
        trace("CXLGTR", _rrfe(3, 0, 1, 0)),
        trace("CFXTR", _rrfe(1, 0, 2, 0)),
        trace("CGXTRA", _rrfe(1, 0, 6, 0)),
        trace("CLGXTR", _rrfe(1, 0, 3, 0)),
    ]

    assert traces == [[SPECIFICATION]] * 6


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CDGTR CXGTR": registers(0, 4),
    "CDGTRA CXGTRA CDFTR CXFTR CDLFTR CXLFTR CDLGTR CXLGTR": _rrfe(0, 1, 4, 4),
    "CGDTR CGXTR": _rrf(4, 1, 0),
    "CFDTR CFXTR CGDTRA CGXTRA CLFDTR CLFXTR CLGDTR CLGXTR": _rrfe(4, 1, 0, 4),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 20
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
